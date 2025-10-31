NETWORK_MAPPING = {
    "ETHEREUM": "ETH", # 'Ethereum(ERC20)'
    'BASEEVM': 'BASE' # 'Base(ERC20)'
}

def get_unified_network_name(token_network: str) -> str:
    normalized_network = token_network.upper()
    for key in NETWORK_MAPPING.keys():
        if  key.upper() in normalized_network:
            return NETWORK_MAPPING[key]

    return token_network.upper()