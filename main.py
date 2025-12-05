"""
Inventory Management System - MCP Server with REST API

This script implements a dual-mode inventory management system:
1. MCP (Model Context Protocol) server for Claude Desktop integration
2. REST API server for HTTP-based access

The system provides full CRUD operations (Create, Read, Update, Delete) for managing
product inventory with persistent storage in JSON format.

Usage:
    - MCP mode (default): python main.py
    - REST API mode: python main.py http
"""

import json
import os
import sys
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# FastAPI imports for REST API functionality
from fastapi import FastAPI, HTTPException, Security, status, Depends, Query, Path
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP  # MCP framework for Claude Desktop integration
import uvicorn

# ============================================================================
# 1. DATA MODELS (Pydantic Schemas)
# ============================================================================
# These models define the structure and validation rules for inventory data.
# Pydantic automatically validates input and generates API documentation.

class Product(BaseModel):
    """Represents a product in the inventory system."""
    product_id: str = Field(..., json_schema_extra={"example": "P-001"})
    name: str = Field(..., json_schema_extra={"example": "Cans of Beer"})
    quantity: int = Field(..., json_schema_extra={"example": 100})
    unit_price: float = Field(..., json_schema_extra={"example": 12.50})

class NewProductRequest(BaseModel):
    """Request model for creating a new product (used by REST API)."""
    name: str = Field(..., json_schema_extra={"example": "Coffee Mugs (Black)"})
    initial_quantity: int = Field(..., json_schema_extra={"example": 25})
    unit_price: float = Field(..., json_schema_extra={"example": 8.00})

class AdjustmentRequest(BaseModel):
    """Request model for stock adjustments (used by REST API)."""
    product_name: str = Field(..., json_schema_extra={"example": "Cans of Beer"}, description="The product name to adjust.")
    quantity_change: int = Field(..., json_schema_extra={"example": 10}, description="Positive to add stock (restock), negative to remove stock (sale/loss).")


# ============================================================================
# 2. DATA PERSISTENCE LAYER
# ============================================================================
# Handles loading and saving inventory data to/from a JSON file.
# Uses absolute paths to ensure the file is found regardless of working directory.

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTORY_FILE = os.path.join(SCRIPT_DIR, "inventory.json")
INVENTORY_DB: Dict[str, Product] = {}  # In-memory database: product_id -> Product 

def load_inventory():
    """
    Loads inventory data from JSON file into memory.
    
    Called on startup and before REST API operations to ensure data consistency.
    If the file doesn't exist or contains invalid JSON, starts with empty inventory.
    """
    global INVENTORY_DB
    if os.path.exists(INVENTORY_FILE):
        try:
            with open(INVENTORY_FILE, 'r') as f:
                data = json.load(f)
                # Convert JSON dict to Product objects
                INVENTORY_DB = {k: Product(**v) for k, v in data.items()}
        except json.JSONDecodeError:
            # If file is corrupted, start fresh
            INVENTORY_DB = {}
    else:
        # File doesn't exist yet - will be created on first save
        pass

def save_inventory():
    """
    Persists current inventory state to JSON file.
    
    Called after every modification (create, update, delete) to ensure data persistence.
    Uses Pydantic's model_dump() to convert Product objects to dictionaries.
    """
    data_to_save = {k: v.model_dump() for k, v in INVENTORY_DB.items()}
    with open(INVENTORY_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=2)

# Load inventory data when the script starts
load_inventory()

def fuzzy_match_product(query: str) -> List[Product]:
    """
    Performs case-insensitive partial name matching to find products.
    
    Args:
        query: Product name or partial name to search for. If None/empty, returns all products.
    
    Returns:
        List of Product objects matching the query (empty list if no matches).
    
    This enables flexible searching - users don't need exact product names.
    """
    if not query:
        return list(INVENTORY_DB.values())

    query_lower = query.lower()
    matches = [
        product for product in INVENTORY_DB.values()
        if query_lower in product.name.lower()
    ]
    return matches

# ============================================================================
# 3. SECURITY CONFIGURATION
# ============================================================================
# API key authentication for REST API endpoints (optional - can be removed if not needed).
# The MCP server doesn't use this - it's only for HTTP REST API access.

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

# API key is read from environment variable MCP_API_KEY, with a default fallback.
# In production, always set this via environment variable for security.
SECRET_API_KEY = os.environ.get("MCP_API_KEY", "super-secret-mcp-key") 

def get_api_key(api_key: str = Security(api_key_header)):
    """
    Validates the API key from request headers.
    
    This function can be used as a dependency in FastAPI routes to protect endpoints.
    Currently not used, but available for future security enhancements.
    """
    if api_key == SECRET_API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )

# ============================================================================
# 4. MCP SERVER SETUP
# ============================================================================
# FastMCP creates an MCP server that Claude Desktop can connect to via stdio.
# The @mcp.tool() decorator automatically exposes functions as MCP tools.

mcp = FastMCP(
    "Inventory Manager (Explicit Tools)",  # Server name shown in Claude Desktop
    json_response=True  # Use JSON format for responses
)

# ============================================================================
# 5. MCP TOOLS (Exposed to Claude Desktop)
# ============================================================================
# These functions are automatically registered as tools that Claude can call.
# Each tool implements one CRUD operation for inventory management.

@mcp.tool()
async def get_inventory_status(
    product_name: Optional[str] = Field(None, description="The name or partial name of the product to search for."), 
) -> List[Product]:
    """
    READ operation: Retrieves inventory status for all products or a specific product.
    
    Uses fuzzy matching, so partial product names work. If no product_name is provided,
    returns all products in the inventory.
    """
    matches = fuzzy_match_product(product_name)

    if not matches and product_name:
        raise ValueError(f"No products found matching '{product_name}'.")
        
    return matches

@mcp.tool()
async def add_new_product(
    name: str = Field(..., description="The name of the product to add."),
    initial_quantity: int = Field(..., description="The initial stock quantity."),
    unit_price: float = Field(..., description="The price per unit."),
) -> Product:
    """
    CREATE operation: Adds a new product to the inventory.
    
    Automatically generates a unique product ID in the format "P-XXXXX" where XXXXX
    is the first segment of a UUID. The product is immediately persisted to disk.
    """
    # Generate unique product ID using UUID
    product_id = "P-" + str(uuid.uuid4()).split('-')[0].upper()
    
    product = Product(
        product_id=product_id,
        name=name,
        quantity=initial_quantity,
        unit_price=unit_price
    )
    
    INVENTORY_DB[product_id] = product
    save_inventory()  # Persist to disk immediately
    
    return product

@mcp.tool()
async def adjust_stock_quantity(
    product_name: str = Field(..., description="The name of the product to adjust."),
    quantity_change: int = Field(..., description="Positive number to increase stock, negative number to decrease stock."),
) -> Product:
    """
    UPDATE operation: Adjusts the stock quantity of an existing product.
    
    - Use positive numbers to increase stock (restocking)
    - Use negative numbers to decrease stock (sales, losses)
    - Prevents stock from going below zero
    - Requires exact or unique partial product name match
    """
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise ValueError(f"Product not found: '{product_name}'. Cannot adjust stock.")

    # Prevent ambiguity - require unique match
    if len(matches) > 1:
        names = [m.name for m in matches]
        raise ValueError(f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify.")

    product_to_adjust = matches[0]
    original_id = product_to_adjust.product_id
    original_name = product_to_adjust.name

    new_quantity = product_to_adjust.quantity + quantity_change

    # Business rule: prevent negative stock
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

@mcp.tool()
async def remove_product(
    product_name: str = Field(..., description="The name of the product to remove."),
):
    """
    DELETE operation: Permanently removes a product from the inventory.
    
    Uses fuzzy matching to find the product. Requires unique match to prevent
    accidental deletion of multiple products. Changes are immediately persisted.
    """
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise ValueError(f"Product not found: '{product_name}'. Cannot remove.")

    # Prevent ambiguity - require unique match
    if len(matches) > 1:
        names = [m.name for m in matches]
        raise ValueError(f"Ambiguous product name: '{product_name}' matched multiple items: {names}. Please clarify.")

    product_to_remove = matches[0]
    original_id = product_to_remove.product_id

    del INVENTORY_DB[original_id]
    save_inventory()
    
    return {"status": "success", "message": f"Product '{product_name}' (ID: {original_id}) has been removed from inventory."}

# ============================================================================
# 6. REST API SERVER SETUP
# ============================================================================
# FastAPI application for HTTP-based access to the inventory system.
# Provides the same CRUD operations as MCP tools, but via standard REST endpoints.
# Interactive API documentation available at /docs (Swagger UI) and /redoc.

app = FastAPI(
    title="Inventory Manager API",
    description="REST API for managing inventory with full CRUD operations",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI documentation
    redoc_url="/redoc"  # ReDoc documentation
)

# ============================================================================
# 7. REST API ENDPOINTS
# ============================================================================
# These endpoints mirror the MCP tools but use HTTP methods (GET, POST, PATCH, DELETE).
# Each endpoint reloads inventory from disk to ensure consistency between MCP and REST API.

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
    # Reload from disk to sync with any changes made via MCP
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
    This is an alias for /api/products to match MCP tool naming convention.
    
    - **product_name**: Optional product name to search for (case-insensitive partial match)
    - Returns list of matching products
    """
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
    Retrieve a specific product by its unique product ID.
    
    Unlike the name-based search, this requires the exact product ID (e.g., "P-001").
    Useful when you know the exact ID from a previous operation.
    
    - **product_id**: The product ID (e.g., "P-001")
    """
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
    CREATE operation: Add a new product to the inventory.
    
    Automatically generates a unique product ID. The product is immediately
    persisted to disk and available for both MCP and REST API access.
    
    - **name**: Product name
    - **initial_quantity**: Starting stock quantity
    - **unit_price**: Price per unit
    """
    # Generate unique product ID using UUID
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
    UPDATE operation: Adjust the stock quantity of a product.
    
    Uses fuzzy matching to find the product. Prevents negative stock levels.
    Requires unique product name match to avoid ambiguity.
    
    - **product_name**: Name of the product (fuzzy match)
    - **quantity_change**: Amount to change (positive = increase, negative = decrease)
    """
    load_inventory()
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"Product not found: '{product_name}'. Cannot adjust stock."
        )
    
    # Prevent ambiguity - require unique match
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
    
    # Business rule: prevent negative stock
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
    DELETE operation: Permanently remove a product from inventory.
    
    Uses fuzzy matching to find the product. Requires unique match to prevent
    accidental deletion. Changes are immediately persisted.
    
    - **product_name**: Name of the product to remove (fuzzy match)
    """
    load_inventory()
    matches = fuzzy_match_product(product_name)
    
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"Product not found: '{product_name}'. Cannot remove."
        )
    
    # Prevent ambiguity - require unique match
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
    """
    Health check endpoint to verify the API is running and accessible.
    
    Returns the current status and total number of products in inventory.
    Useful for monitoring and load balancer health checks.
    """
    return {
        "status": "healthy",
        "total_products": len(INVENTORY_DB)
    }

# ============================================================================
# 8. SERVER EXECUTION
# ============================================================================
# The script can run in two modes:
# 1. MCP mode (default): For Claude Desktop integration via stdio
# 2. HTTP mode: For REST API access via web browser/HTTP client

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        # HTTP REST API mode: Run FastAPI server with uvicorn
        print("Starting Inventory Manager REST API server...")
        print("Swagger docs available at: http://localhost:8000/docs")
        print("API available at: http://localhost:8000/api")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # MCP mode (default): Run as stdio server for Claude Desktop
        # Claude Desktop communicates with MCP servers via standard input/output
        mcp.run(transport="stdio")