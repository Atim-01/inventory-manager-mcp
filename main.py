import json
import os
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# FastAPI imports for models, exceptions, and security
from fastapi import FastAPI, HTTPException, Security, status, Depends 
from fastapi.security.api_key import APIKeyHeader
from mcp.server.fastmcp import FastMCP # <-- IMPORT THE MCP FRAMEWORK

# --- 1. Pydantic Data Models ---
class Product(BaseModel):
    # Fixed deprecated Pydantic Field usage
    product_id: str = Field(..., json_schema_extra={"example": "P-001"})
    name: str = Field(..., json_schema_extra={"example": "Cans of Beer"})
    quantity: int = Field(..., json_schema_extra={"example": 100})
    unit_price: float = Field(..., json_schema_extra={"example": 12.50})

class NewProductRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Coffee Mugs (Black)"})
    initial_quantity: int = Field(..., json_schema_extra={"example": 25})
    unit_price: float = Field(..., json_schema_extra={"example": 8.00})

class AdjustmentRequest(BaseModel):
    product_name: str = Field(..., json_schema_extra={"example": "Cans of Beer"}, description="The product name to adjust.")
    quantity_change: int = Field(..., json_schema_extra={"example": 10}, description="Positive to add stock (restock), negative to remove stock (sale/loss).")


# --- 2. Data Persistence Layer & Helpers ---
# Use absolute path based on script location to ensure file is found regardless of working directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTORY_FILE = os.path.join(SCRIPT_DIR, "inventory.json")
INVENTORY_DB: Dict[str, Product] = {} 

def load_inventory():
    """Loads inventory from JSON file on server startup. Removed prints for clean startup."""
    global INVENTORY_DB
    if os.path.exists(INVENTORY_FILE):
        try:
            with open(INVENTORY_FILE, 'r') as f:
                data = json.load(f)
                INVENTORY_DB = {k: Product(**v) for k, v in data.items()}
                # Removed print statement
        except json.JSONDecodeError:
            # Removed print statement
            INVENTORY_DB = {}
    else:
        pass

def save_inventory():
    """Saves current INVENTORY_DB to JSON file. Removed print for clean operation."""
    data_to_save = {k: v.model_dump() for k, v in INVENTORY_DB.items()}
    with open(INVENTORY_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=2)
    # Removed print statement

# Execute load on application start
load_inventory()

# Helper function for fuzzy searching
def fuzzy_match_product(query: str) -> List[Product]:
    """Finds products whose names contain the query string (case-insensitive)."""
    if not query:
        return list(INVENTORY_DB.values())

    query_lower = query.lower()
    matches = [
        product for product in INVENTORY_DB.values()
        if query_lower in product.name.lower()
    ]
    return matches

# --- 3. Security Setup ---
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

# Read from environment variable, for use with Claude Desktop configuration
SECRET_API_KEY = os.environ.get("MCP_API_KEY", "super-secret-mcp-key") 

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == SECRET_API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )

# --- 4. Core Server Setup (Define MCP instance first) ---
mcp = FastMCP(
    "Inventory Manager (Explicit Tools)", 
    json_response=True 
)

# --- 5. Explicit Tool Endpoints (USING @mcp.tool()) ---

## Tool 1: GET (Read/Query) Inventory
@mcp.tool()
async def get_inventory_status(
    product_name: Optional[str] = Field(None, description="The name or partial name of the product to search for."), 
    # API KEY REMOVED TEMPORARILY FOR CONNECTION STABILITY
) -> List[Product]:
    """ 
    Retrieves the current stock and details for all products or a specific product 
    using fuzzy matching (The READ operation).
    """
    matches = fuzzy_match_product(product_name)

    if not matches and product_name:
        raise HTTPException(
            status_code=404, 
            detail=f"No products found matching '{product_name}'."
        )
        
    return matches

## Tool 2: CREATE (Add New Product)
@mcp.tool()
async def add_new_product(
    name: str = Field(..., description="The name of the product to add."),
    initial_quantity: int = Field(..., description="The initial stock quantity."),
    unit_price: float = Field(..., description="The price per unit."),
) -> Product:
    """ Adds a completely new item to the store's inventory (The CREATE operation)."""
    
    product_id = "P-" + str(uuid.uuid4()).split('-')[0].upper()
    
    product = Product(
        product_id=product_id,
        name=name,
        quantity=initial_quantity,
        unit_price=unit_price
    )
    
    INVENTORY_DB[product_id] = product
    save_inventory() 
    
    return product

## Tool 3: UPDATE (Adjust Stock)
@mcp.tool()
async def adjust_stock_quantity(
    product_name: str = Field(..., description="The name of the product to adjust."),
    quantity_change: int = Field(..., description="Positive number to increase stock, negative number to decrease stock."),
) -> Product:
    """ Adds or subtracts a quantity from an existing product's stock level (The UPDATE operation)."""
    
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise HTTPException(status_code=404, detail=f"Product not found: '{product_name}'. Cannot adjust stock.")

    if len(matches) > 1:
        names = [m.name for m in matches]
        raise HTTPException(status_code=400, detail=f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify.")

    product_to_adjust = matches[0]
    original_id = product_to_adjust.product_id
    original_name = product_to_adjust.name

    new_quantity = product_to_adjust.quantity + quantity_change

    if new_quantity < 0:
        raise HTTPException(status_code=400, detail=f"Cannot process adjustment. Stock level for '{original_name}' would be negative ({new_quantity}).")

    updated_product = Product(
        product_id=original_id,
        name=original_name,
        quantity=new_quantity,
        unit_price=product_to_adjust.unit_price
    )
    
    INVENTORY_DB[original_id] = updated_product
    save_inventory()
    
    return updated_product

## Tool 4: DELETE (Remove Product)
@mcp.tool()
async def remove_product(
    product_name: str = Field(..., description="The name of the product to remove."), # Query parameter, required
    # API KEY REMOVED TEMPORARILY FOR CONNECTION STABILITY
):
    """ Permanently removes a product from the inventory using fuzzy matching (The DELETE operation)."""
    
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise HTTPException(
            status_code=404, 
            detail=f"Product not found: '{product_name}'. Cannot remove."
        )

    if len(matches) > 1:
        names = [m.name for m in matches]
        raise HTTPException(
            status_code=400,
            detail=f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify."
        )

    product_to_remove = matches[0]
    original_id = product_to_remove.product_id

    del INVENTORY_DB[original_id]
    save_inventory()
    
    return

# --- 6. Server Execution ---
if __name__ == "__main__":
    mcp.run(transport="stdio")