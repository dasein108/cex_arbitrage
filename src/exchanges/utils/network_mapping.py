NETWORK_MAPPING = {
    "ethereum": "ETH", # 'Ethereum(ERC20)'
    'baseevm': 'BASE' # 'Base(ERC20)'
}

def get_unified_network_name(token_network: str) -> str:
    normalized_network = token_network.lower()
    for key in NETWORK_MAPPING.keys():
        if  key.lower() in normalized_network:
            return NETWORK_MAPPING[key]

    return token_network