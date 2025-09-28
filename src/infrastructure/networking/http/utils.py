"""
HTTP Networking Utilities

REFACTORING NOTE: The centralized `create_rest_transport_manager` factory function
has been removed as part of the REST architecture refactoring. Each exchange
implementation now creates its own REST manager via the `create_rest_manager`
abstract method in BaseRestInterface.

This file is preserved as a placeholder for future HTTP utilities.
"""

# File intentionally minimal after factory function removal
# Future HTTP utilities can be added here as needed