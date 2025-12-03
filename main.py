import json
import os
import sys
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# FastAPI imports for models, exceptions, and security
from fastapi import FastAPI, HTTPException, Security, status, Depends, Query, Path
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP # <-- IMPORT THE MCP FRAMEWORK
import uvicorn

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
        raise ValueError(f"No products found matching '{product_name}'.")
        
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
        raise ValueError(f"Product not found: '{product_name}'. Cannot adjust stock.")

    if len(matches) > 1:
        names = [m.name for m in matches]
        raise ValueError(f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify.")

    product_to_adjust = matches[0]
    original_id = product_to_adjust.product_id
    original_name = product_to_adjust.name

    new_quantity = product_to_adjust.quantity + quantity_change

    if new_quantity < 0:
        raise ValueError(f"Cannot process adjustment. Stock level for '{original_name}' would be negative ({new_quantity}).")

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
        raise ValueError(f"Product not found: '{product_name}'. Cannot remove.")

    if len(matches) > 1:
        names = [m.name for m in matches]
        raise ValueError(f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify.")

    product_to_remove = matches[0]
    original_id = product_to_remove.product_id

    del INVENTORY_DB[original_id]
    save_inventory()
    
    return {"status": "success", "message": f"Product '{product_name}' (ID: {original_id}) has been removed from inventory."}

# --- 6. FastAPI REST API Setup ---
app = FastAPI(
    title="Inventory Manager API",
    description="REST API for managing inventory with full CRUD operations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# --- 7. REST API Endpoints ---

@app.get("/api/products", 
         response_model=List[Product],
         summary="Get all products or search by name",
         tags=["Products"])
async def get_products(
    name: Optional[str] = Query(None, description="Filter products by name (fuzzy match)")
):
    """
    Retrieve all products or search for products by name.
    
    - **name**: Optional product name to search for (case-insensitive partial match)
    - Returns list of matching products
    """
    # Reload from file to ensure we have the latest data (in case MCP added products)
    load_inventory()
    matches = fuzzy_match_product(name)
    
    if not matches and name:
        raise HTTPException(
            status_code=404,
            detail=f"No products found matching '{name}'."
        )
    
    return matches

@app.get("/api/inventory/status",
         response_model=List[Product],
         summary="Get inventory status (alias for /api/products)",
         tags=["Products"])
async def get_inventory_status(
    product_name: Optional[str] = Query(None, alias="name", description="Filter products by name (fuzzy match)")
):
    """
    Retrieve inventory status - all products or search by name.
    This is an alias for /api/products to match MCP tool naming.
    
    - **product_name**: Optional product name to search for (case-insensitive partial match)
    - Returns list of matching products
    """
    # Reload from file to ensure we have the latest data (in case MCP added products)
    load_inventory()
    matches = fuzzy_match_product(product_name)
    
    if not matches and product_name:
        raise HTTPException(
            status_code=404,
            detail=f"No products found matching '{product_name}'."
        )
    
    return matches

@app.get("/api/products/{product_id}",
         response_model=Product,
         summary="Get product by ID",
         tags=["Products"])
async def get_product_by_id(product_id: str = Path(..., description="Product ID")):
    """
    Retrieve a specific product by its ID.
    
    - **product_id**: The product ID (e.g., "P-001")
    """
    # Reload from file to ensure we have the latest data
    load_inventory()
    if product_id not in INVENTORY_DB:
        raise HTTPException(
            status_code=404,
            detail=f"Product with ID '{product_id}' not found."
        )
    return INVENTORY_DB[product_id]

@app.post("/api/products",
          response_model=Product,
          status_code=status.HTTP_201_CREATED,
          summary="Add a new product",
          tags=["Products"])
async def create_product(product: NewProductRequest):
    """
    Add a new product to the inventory.
    
    - **name**: Product name
    - **initial_quantity**: Starting stock quantity
    - **unit_price**: Price per unit
    """
    product_id = "P-" + str(uuid.uuid4()).split('-')[0].upper()
    
    new_product = Product(
        product_id=product_id,
        name=product.name,
        quantity=product.initial_quantity,
        unit_price=product.unit_price
    )
    
    INVENTORY_DB[product_id] = new_product
    save_inventory()
    
    return new_product

@app.patch("/api/products/{product_name}/stock",
           response_model=Product,
           summary="Adjust product stock quantity",
           tags=["Products"])
async def adjust_stock(
    product_name: str = Path(..., description="Product name to adjust"),
    quantity_change: int = Query(..., description="Positive to increase, negative to decrease")
):
    """
    Adjust the stock quantity of a product.
    
    - **product_name**: Name of the product (fuzzy match)
    - **quantity_change**: Amount to change (positive = increase, negative = decrease)
    """
    # Reload from file to ensure we have the latest data
    load_inventory()
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"Product not found: '{product_name}'. Cannot adjust stock."
        )
    
    if len(matches) > 1:
        names = [m.name for m in matches]
        raise HTTPException(
            status_code=400,
            detail=f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify."
        )
    
    product_to_adjust = matches[0]
    original_id = product_to_adjust.product_id
    original_name = product_to_adjust.name
    
    new_quantity = product_to_adjust.quantity + quantity_change
    
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process adjustment. Stock level for '{original_name}' would be negative ({new_quantity})."
        )
    
    updated_product = Product(
        product_id=original_id,
        name=original_name,
        quantity=new_quantity,
        unit_price=product_to_adjust.unit_price
    )
    
    INVENTORY_DB[original_id] = updated_product
    save_inventory()
    
    return updated_product

@app.delete("/api/products/{product_name}",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Remove a product",
            tags=["Products"])
async def delete_product(
    product_name: str = Path(..., description="Product name to remove")
):
    """
    Permanently remove a product from inventory.
    
    - **product_name**: Name of the product to remove (fuzzy match)
    """
    # Reload from file to ensure we have the latest data
    load_inventory()
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
    
    return None

@app.get("/api/health",
         summary="Health check endpoint",
         tags=["Health"])
async def health_check():
    """Health check endpoint to verify API is running."""
    return {
        "status": "healthy",
        "total_products": len(INVENTORY_DB)
    }

# --- 8. Server Execution ---
if __name__ == "__main__":
    # Check command line arguments to determine mode
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        # Run as HTTP REST API server
        print("Starting Inventory Manager REST API server...")
        print("Swagger docs available at: http://localhost:8000/docs")
        print("API available at: http://localhost:8000/api")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # Default: Run as MCP server (stdio) for Claude Desktop
        mcp.run(transport="stdio")