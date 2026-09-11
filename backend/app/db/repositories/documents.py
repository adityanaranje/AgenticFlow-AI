from typing import Any

from app.db.supabase import get_supabase

class DocumentRepository:
    """Repository for document metadata."""
    def create(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("documents")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def get_by_checksum(
        self,
        organization_id: str,
        checksum: str,
    ) -> dict[str, Any] | None:
        """Return the organization's document with this content checksum
        (mirrors the ``documents_org_checksum_idx`` unique index), if any."""
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("documents")
            .select("*")
            .eq("organization_id", organization_id)
            .eq("checksum", checksum)
            .maybe_single()
            .execute()
        )

        return response.data

    def get_by_id(
        self,
        document_id: str,
        organization_id: str,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("documents")
            .select("*")
            .eq("id", document_id)
            .eq("organization_id", organization_id)
            .maybe_single()
            .execute()
        )

        return response.data

    def list_for_organization(
        self,
        organization_id: str,
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("documents")
            .select("*")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    def update_status(
        self,
        document_id: str,
        organization_id: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        payload: dict[str, Any] = {
            "status": status,
        }

        if metadata is not None:
            payload["metadata"] = metadata

        response = (
            client.table("documents")
            .update(payload)
            .eq("id", document_id)
            .eq("organization_id", organization_id)
            .select("*")
            .maybe_single()
            .execute()
        )

        return response.data

    def create_chunk(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("document_chunks")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def list_chunks(
        self,
        document_id: str,
        organization_id: str,
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("document_chunks")
            .select("*")
            .eq("document_id", document_id)
            .eq("organization_id", organization_id)
            .order("chunk_index")
            .execute()
        )

        return response.data or []

    def count_chunks(
        self,
        document_id: str,
        organization_id: str,
    ) -> int:
        """Return the number of chunks stored for a document."""
        client = get_supabase()

        if client is None:
            return 0

        response = (
            client.table("document_chunks")
            .select("id", count="exact", head=True)
            .eq("document_id", document_id)
            .eq("organization_id", organization_id)
            .execute()
        )

        return int(response.count or 0)

    def get_document(
        self,
        document_id: str,
    ) -> dict[str, Any] | None:
        """Look up a document by id only (no org filter). Callers MUST
        authorize the organization before using the result."""
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("documents")
            .select("*")
            .eq("id", document_id)
            .maybe_single()
            .execute()
        )

        return response.data

    def update(
        self,
        document_id: str,
        organization_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply an arbitrary set of columns to a document."""
        client = get_supabase()

        if client is None:
            return None

        if not fields:
            return None

        response = (
            client.table("documents")
            .update(fields)
            .eq("id", document_id)
            .eq("organization_id", organization_id)
            .select("*")
            .maybe_single()
            .execute()
        )

        return response.data

    def delete_chunks(
        self,
        document_id: str,
        organization_id: str,
    ) -> None:
        """Remove all chunk rows for a document (idempotent re-processing)."""
        client = get_supabase()
        if client is None:
            return
        try:
            client.table("document_chunks").delete().eq(
                "document_id", document_id
            ).eq("organization_id", organization_id).execute()
        except Exception:
            from app.core.logging import get_logger as _lg

            _lg(__name__).exception(
                "Failed to delete chunks for document %s", document_id
            )

    def delete(
        self,
        document_id: str,
        organization_id: str,
    ) -> bool:
        client = get_supabase()

        if client is None:
            return False

        response = (
            client.table("documents")
            .delete()
            .eq("id", document_id)
            .eq("organization_id", organization_id)
            .execute()
        )

        return bool(response.data)
