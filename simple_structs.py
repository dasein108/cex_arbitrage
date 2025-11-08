"""
Simple structs for optimization testing to avoid import chain issues
"""

class AssetName:
    def __init__(self, name: str):
        self.name = name
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"AssetName('{self.name}')"

class Symbol:
    def __init__(self, base: AssetName, quote: AssetName):
        self.base = base
        self.quote = quote
    
    def __str__(self):
        return f"{self.base}_{self.quote}"
    
    def __repr__(self):
        return f"Symbol(base={self.base}, quote={self.quote})"