from exchanges.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper

class MexcProtobufParser:
    """Shared protobuf parsing utilities for MEXC WebSocket messages.

    Consolidates protobuf parsing logic between public and private implementations
    to eliminate code duplication and ensure consistent handling.
    """

    @staticmethod
    def extract_symbol_from_protobuf(data: bytes) -> str:
        """Fast symbol extraction from protobuf data."""
        try:
            # Method 1: Extract from channel name at start of message
            # MEXC V3 format: b'\n.spot@public.aggre.depth.v3.api.pb@100ms@BTCUSDT\x1a\x07BTCUSDT...'
            data_str = data.decode('utf-8', errors='ignore')
            if '@' in data_str:
                parts = data_str.split('@')
                if len(parts) >= 4:
                    # Last part before \x1a should be symbol
                    symbol_part = parts[3].split('\x1a')[0]
                    if symbol_part:
                        return symbol_part.strip()

            # Method 2: Look for symbol field marker 0x1a (actual byte, not literal)
            symbol_idx = data.find(b'\x1a')
            if symbol_idx != -1 and symbol_idx + 1 < len(data):
                symbol_len = data[symbol_idx + 1]
                if symbol_idx + 2 + symbol_len <= len(data):
                    symbol = data[symbol_idx + 2:symbol_idx + 2 + symbol_len].decode('utf-8', errors='ignore')
                    if symbol:
                        return symbol

        except Exception:
            pass
        return ""

    @staticmethod
    def parse_wrapper_message(data: bytes) -> PushDataV3ApiWrapper:
        """Parse raw bytes into PushDataV3ApiWrapper."""
        wrapper = PushDataV3ApiWrapper()
        wrapper.ParseFromString(data)
        return wrapper
