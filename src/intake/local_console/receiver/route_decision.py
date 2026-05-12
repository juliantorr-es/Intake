"""Upload Route Decision Service.

Determines where uploads should be routed based on receiver availability.

Priority order:
1. Local receiver if online and handshake succeeds
2. Fallback provider if configured
3. Quote submission without files or retry-later state
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from intake.deploy.models_upload import (
    UploadProviderKind,
    UploadRouteDecision as BaseUploadRouteDecision,
)
from intake.local_console.receiver.models import (
    ReceiverHandshakeChallenge,
    ReceiverHandshakeResponse,
    ReceiverStatus,
)
from intake.local_console.receiver.service import LocalReceiverService


class RouteDecisionError(Exception):
    """Error during route decision."""
    pass


class UploadRouteDecision(BaseUploadRouteDecision):
    """Extended route decision with local receiver support."""
    
    # Additional fields for local receiver decisions
    receiver_handshake_success: bool = False
    receiver_handshake_latency_ms: Optional[float] = None
    receiver_endpoint: Optional[str] = None


class UploadRouteDecisionService:
    """Service for making upload routing decisions.
    
    This service determines where uploads should go based on:
    - Local receiver availability (via handshake)
    - Fallback provider configuration
    - Request requirements
    """
    
    def __init__(self, receiver_service: Optional[LocalReceiverService] = None):
        """Initialize route decision service.
        
        Args:
            receiver_service: Optional receiver service instance
        """
        self.receiver_service = receiver_service
        self._fallback_provider: Optional[UploadProviderKind] = None
    
    def set_fallback_provider(self, provider: UploadProviderKind) -> None:
        """Set the fallback provider to use when local is unavailable."""
        self._fallback_provider = provider
    
    def unset_fallback_provider(self) -> None:
        """Clear the fallback provider."""
        self._fallback_provider = None
    
    def get_fallback_provider(self) -> Optional[UploadProviderKind]:
        """Get the currently configured fallback provider."""
        return self._fallback_provider
    
    # =========================================================================
    # Handshake
    # =========================================================================
    
    def create_handshake_challenge(self) -> ReceiverHandshakeChallenge:
        """Create a handshake challenge for receiver verification."""
        return ReceiverHandshakeChallenge()
    
    def attempt_receiver_handshake(
        self,
        challenge: Optional[ReceiverHandshakeChallenge] = None,
        timeout_seconds: float = 2.0,
    ) -> tuple[bool, Optional[ReceiverHandshakeResponse]]:
        """Attempt handshake with local receiver.
        
        Args:
            challenge: Optional challenge to send
            timeout_seconds: Connection timeout
            
        Returns:
            Tuple of (success, handshake_response or None)
        """
        import time
        
        start_time = time.time()
        
        try:
            if self.receiver_service:
                response = self.receiver_service.perform_handshake(challenge)
                elapsed_ms = (time.time() - start_time) * 1000
                
                # Check if response indicates online status
                if response.status == ReceiverStatus.ONLINE:
                    return True, response
                else:
                    return False, response
            else:
                # No receiver service configured - simulate offline
                return False, None
        except Exception:
            return False, None
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
    
    # =========================================================================
    # Route Decision
    # =========================================================================
    
    def decide_upload_route(
        self,
        quote_id: str,
        requested_content_types: list[str],
        requested_max_file_size: int,
        use_fallback: bool = True,
    ) -> UploadRouteDecision:
        """Decide where to route an upload.
        
        Priority:
        1. Local receiver if online and supports requested upload type
        2. Fallback provider if configured
        3. Return retry_later/quote_without_files decision
        
        Args:
            quote_id: The quote identifier
            requested_content_types: Content types the client wants to upload
            requested_max_file_size: Maximum file size needed
            use_fallback: Whether to allow fallback to configured provider
            
        Returns:
            UploadRouteDecision with chosen route and details
        """
        import time
        
        start_time = time.time()
        
        # Try local receiver first
        handshake_success, handshake_response = self.attempt_receiver_handshake()
        handshake_latency = (time.time() - start_time) * 1000
        
        if handshake_success and handshake_response:
            # Check if receiver supports requested parameters
            if self._can_receiver_handle(
                handshake_response, requested_content_types, requested_max_file_size
            ):
                return UploadRouteDecision(
                    chosen_provider=UploadProviderKind.LOCAL_LOOPBACK_DEV,
                    route_priority=1,
                    route_reason="local_receiver_online_and_capable",
                    fallback_available=bool(self._fallback_provider),
                    fallback_provider=self._fallback_provider,
                    upload_endpoint="/receiver/uploads",
                    upload_session={"type": "local_loopback"},
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                    receiver_handshake_success=True,
                    receiver_handshake_latency_ms=handshake_latency,
                    receiver_endpoint="http://127.0.0.1:8001/receiver",
                )
        
        # Local receiver not available or not capable - try fallback
        if use_fallback and self._fallback_provider:
            return UploadRouteDecision(
                chosen_provider=self._fallback_provider,
                route_priority=2,
                route_reason="local_receiver_offline_fallback_configured",
                fallback_available=True,
                fallback_provider=self._fallback_provider,
                upload_endpoint="/upload",
                upload_session={"type": "fallback", "provider": self._fallback_provider.value},
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                receiver_handshake_success=False,
                receiver_handshake_latency_ms=handshake_latency,
            )
        
        # No fallback available - return retry/quote-without-files decision
        return UploadRouteDecision(
            chosen_provider=UploadProviderKind.HOSTED_BUFFER_FUTURE,
            route_priority=3,
            route_reason="no_local_receiver_no_fallback",
            fallback_available=False,
            fallback_provider=None,
            upload_endpoint="",
            upload_session={"type": "retry_later"},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            receiver_handshake_success=False,
            receiver_handshake_latency_ms=handshake_latency,
        )
    
    def decide_upload_route_with_session(
        self,
        quote_id: str,
        session_id: str,
        account_id: Optional[str] = None,
    ) -> UploadRouteDecision:
        """Decide route for an existing upload session.
        
        Args:
            quote_id: The quote identifier
            session_id: The existing session ID
            account_id: Optional account identifier
            
        Returns:
            UploadRouteDecision
        """
        # For now, same logic as regular decision
        # In future, this could look up session details
        return self.decide_upload_route(
            quote_id=quote_id,
            requested_content_types=[],
            requested_max_file_size=0,
        )
    
    def _can_receiver_handle(
        self,
        handshake: ReceiverHandshakeResponse,
        content_types: list[str],
        max_file_size: int,
    ) -> bool:
        """Check if receiver can handle the requested upload.
        
        Args:
            handshake: Handshake response from receiver
            content_types: Requested content types
            max_file_size: Maximum file size needed
            
        Returns:
            True if receiver can handle, False otherwise
        """
        if not handshake or handshake.status != ReceiverStatus.ONLINE:
            return False
        
        # Check multipart protocol support
        if "multipart" not in handshake.supported_protocols:
            return False
        
        # Check content type support
        if content_types:
            for ct in content_types:
                if ct not in handshake.supported_content_types:
                    return False
        
        # Check file size limit
        if max_file_size > 0 and max_file_size > handshake.max_file_size_bytes:
            return False
        
        return True
    
    def get_receiver_status(self) -> str:
        """Get a string description of receiver status."""
        if self.receiver_service:
            status = self.receiver_service.get_availability().status
            return status.value
        return "not_configured"
    
    @property
    def receiver_configured(self) -> bool:
        """Whether a receiver service is configured."""
        return self.receiver_service is not None
    
    @property
    def receiver_online(self) -> bool:
        """Whether the receiver appears to be online."""
        if not self.receiver_service:
            return False
        status = self.receiver_service.get_availability().status
        return status == ReceiverStatus.ONLINE
    
    @property
    def fallback_configured(self) -> bool:
        """Whether a fallback provider is configured."""
        return self._fallback_provider is not None


# Global singleton
def get_route_decision_service() -> UploadRouteDecisionService:
    """Get the global route decision service."""
    # Import here to avoid circular imports
    from intake.local_console.receiver.service import LocalReceiverService
    
    # Create service with default receiver
    receiver_service = LocalReceiverService()
    return UploadRouteDecisionService(receiver_service=receiver_service)
