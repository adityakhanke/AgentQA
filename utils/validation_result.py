import time
from typing import Optional, Dict, Any

class ValidationResult:
    """Container for validation results with detailed metrics."""
    def __init__(
        self,
        success: bool,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.message = message
        self.details = details or {}
        self.evidence = evidence or {}
        self.attempts = 1
        self.duration_ms = 0
        self.start_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for tool response."""
        self.duration_ms = int((time.time() - self.start_time) * 1000)

        result = {
            "message": "Success" if self.success else "Failure",
            "details" if self.success else "error": self.message,
            "verified": self.success,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms
        }

        # Add additional details
        if self.details:
            result["validation_details"] = self.details

        # Add evidence if available
        if self.evidence:
            for key, value in self.evidence.items():
                result[key] = value

        return result