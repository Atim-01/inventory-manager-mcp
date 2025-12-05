# Complete Step-by-Step Guide: Building an MCP Server from Scratch

## Overview

This guide will walk you through building a complete MCP (Model Context Protocol) server with REST API capabilities for inventory management. We'll use `uv` as the Python package manager and build everything step-by-step.

## Prerequisites

- Python 3.13 or higher installed
- Basic understanding of Python syntax
- Terminal/Command Prompt access

---

## Phase 1: Project Setup and Environment

### Step 1.1: Install uv Package Manager

**Why:** `uv` is a fast, modern Python package manager that handles dependencies efficiently.

**Action:**

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or using pip (if you have it)
pip install uv
```

**Verify installation:**

```bash
uv --version
```

### Step 1.2: Create Project Directory

**Why:** Organize your project in a dedicated folder.

**Action:**

```bash
mkdir inventory-mcp
cd inventory-mcp
```

### Step 1.3: Initialize Python Project with uv

**Why:** Creates project structure and dependency management files.

**Action:**

````bash
# Windows (PowerShell)

# Create a new directory for our project

uv init ${PROJECT_NAME}
cd ${PROJECT_NAME}

# Create virtual environment and activate it
uv venv
source .venv/bin/activate

# Install dependencies
uv add "mcp[cli]" httpx
```

This creates:

- `pyproject.toml` - Project configuration and dependencies
- `.python-version` - Python version specification

### Step 1.4: Create Main Python File

**Why:** This will be our main server file.

**Action:**

```bash
# Create main.py (empty file to start)
touch main.py  # Linux/Mac
# Or on Windows PowerShell:
New-Item main.py -ItemType File
````

---

## Phase 2: Understanding and Adding Dependencies

### Step 2.1: Configure Dependencies in pyproject.toml

**Why:** Define all required packages in one place for easy management.

**Action:** Edit `pyproject.toml`:

```toml
[project]
name = "inventory-mcp"
version = "0.1.0"
description = "Inventory Management MCP Server with REST API"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "mcp[cli]>=1.22.0",        # MCP framework for Claude Desktop
    "fastapi>=0.104.0",        # REST API framework
    "uvicorn[standard]>=0.24.0",  # ASGI server for FastAPI
    "pydantic>=2.0.0",         # Data validation (usually included with FastAPI)
]
```

**Explanation of each dependency:**

- `mcp[cli]`: Provides FastMCP class for creating MCP servers that Claude Desktop can connect to
- `fastapi`: Modern web framework for building REST APIs with automatic documentation
- `uvicorn`: ASGI server to run FastAPI applications
- `pydantic`: Data validation library (auto-installed with FastAPI, but explicit is better)

### Step 2.2: Install Dependencies

**Why:** Download and install all required packages.

**Action:**

```bash
uv sync
```

This creates:

- `uv.lock` - Locked dependency versions
- Virtual environment (managed by uv)

---

## Phase 3: Building the Code - Understanding the Structure

### Step 3.1: Standard Library Imports (Lines 16-22)

**Why:** These are built-in Python modules - no installation needed.

**Add to main.py:**

```python
import json          # For reading/writing JSON files (data persistence)
import os            # For file path operations
import sys           # For command-line arguments (http vs mcp mode)
import uuid          # For generating unique product IDs
from typing import Dict, List, Optional  # Type hints for better code clarity
from datetime import datetime  # For timestamps (if needed later)
```

**Why each import:**

- `json`: Store inventory data in JSON format
- `os`: Get script directory for file paths
- `sys`: Check command-line arguments to switch between MCP/HTTP modes
- `uuid`: Generate unique product IDs
- `typing`: Type hints help catch errors and document code
- `datetime`: For future features like audit logs

### Step 3.2: Third-Party Imports (Lines 21-29)

**Why:** These require installation via uv.

**Add to main.py:**

```python
from pydantic import BaseModel, Field  # Data models with validation
from fastapi import FastAPI, HTTPException, Security, status, Depends, Query, Path
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP  # MCP server framework
import uvicorn  # Web server for FastAPI
```

**Why each import:**

- `pydantic.BaseModel`: Create data models with automatic validation
- `pydantic.Field`: Add descriptions and examples to model fields
- `fastapi.FastAPI`: Main application class for REST API
- `fastapi.HTTPException`: Raise HTTP errors (404, 400, etc.)
- `fastapi.Query/Path`: Extract parameters from URL
- `FastMCP`: Create MCP server that Claude Desktop connects to
- `uvicorn`: Run the FastAPI server

---

## Phase 4: Data Models (Pydantic Schemas)

### Step 4.1: Product Model

**Why:** Define the structure of inventory items with validation.

**Add to main.py:**

```python
class Product(BaseModel):
    """Represents a product in the inventory system."""
    product_id: str = Field(..., json_schema_extra={"example": "P-001"})
    name: str = Field(..., json_schema_extra={"example": "Cans of Beer"})
    quantity: int = Field(..., json_schema_extra={"example": 100})
    unit_price: float = Field(..., json_schema_extra={"example": 12.50})
```

**Explanation:**

- `BaseModel`: Pydantic base class that adds validation
- `Field(...)`: Required field (ellipsis means required)
- `json_schema_extra`: Examples for API documentation
- Type hints (`str`, `int`, `float`): Automatic type validation

### Step 4.2: Request Models for REST API

**Why:** Separate models for API requests (different from internal Product model).

**Add to main.py:**

```python
class NewProductRequest(BaseModel):
    """Request model for creating a new product (used by REST API)."""
    name: str = Field(..., json_schema_extra={"example": "Coffee Mugs (Black)"})
    initial_quantity: int = Field(..., json_schema_extra={"example": 25})
    unit_price: float = Field(..., json_schema_extra={"example": 8.00})

class AdjustmentRequest(BaseModel):
    """Request model for stock adjustments (used by REST API)."""
    product_name: str = Field(..., description="The product name to adjust.")
    quantity_change: int = Field(..., description="Positive to add stock, negative to remove stock.")
```

**Why separate models:**

- API users don't provide `product_id` (we generate it)
- Cleaner API design - only request what's needed

---

## Phase 5: Data Persistence Layer

### Step 5.1: File Path Configuration

**Why:** Store inventory data in a JSON file in the same directory as the script.

**Add to main.py:**

```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTORY_FILE = os.path.join(SCRIPT_DIR, "inventory.json")
INVENTORY_DB: Dict[str, Product] = {}  # In-memory database: product_id -> Product
```

**Explanation:**

- `os.path.abspath(__file__)`: Get absolute path of main.py
- `os.path.dirname()`: Get directory containing main.py
- `os.path.join()`: Create path to inventory.json (works on all OS)
- `INVENTORY_DB`: Dictionary storing products in memory (fast access)

### Step 5.2: Load Inventory Function

**Why:** Read saved data from JSON file when server starts.

**Add to main.py:**

```python
def load_inventory():
    """Loads inventory data from JSON file into memory."""
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
```

**Explanation:**

- `global INVENTORY_DB`: Modify the global variable
- `os.path.exists()`: Check if file exists
- `json.load()`: Parse JSON file
- `Product(**v)`: Convert dict to Product object (Pydantic validation)
- `try/except`: Handle corrupted files gracefully

### Step 5.3: Save Inventory Function

**Why:** Persist changes to disk after every modification.

**Add to main.py:**

```python
def save_inventory():
    """Persists current inventory state to JSON file."""
    data_to_save = {k: v.model_dump() for k, v in INVENTORY_DB.items()}
    with open(INVENTORY_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=2)
```

**Explanation:**

- `model_dump()`: Convert Pydantic model to dictionary
- `json.dump()`: Write JSON to file
- `indent=2`: Pretty formatting for readability

### Step 5.4: Load on Startup

**Why:** Load existing data when server starts.

**Add to main.py:**

```python
load_inventory()  # Load inventory data when the script starts
```

### Step 5.5: Fuzzy Search Function

**Why:** Allow partial product name matching (user-friendly).

**Add to main.py:**

```python
def fuzzy_match_product(query: str) -> List[Product]:
    """Performs case-insensitive partial name matching to find products."""
    if not query:
        return list(INVENTORY_DB.values())

    query_lower = query.lower()
    matches = [
        product for product in INVENTORY_DB.values()
        if query_lower in product.name.lower()
    ]
    return matches
```

**Explanation:**

- `-> List[Product]`: Return type hint
- List comprehension: Filter products where query matches name
- Case-insensitive: Convert both to lowercase for comparison

---

## Phase 6: MCP Server Setup

### Step 6.1: Initialize FastMCP Server

**Why:** Create the MCP server that Claude Desktop connects to.

**Add to main.py:**

```python
mcp = FastMCP(
    "Inventory Manager (Explicit Tools)",  # Server name shown in Claude Desktop
    json_response=True  # Use JSON format for responses
)
```

**Explanation:**

- `FastMCP`: Framework that handles MCP protocol communication
- Server name: Appears in Claude Desktop's MCP server list
- `json_response=True`: Use JSON format (standard for MCP)

---

## Phase 7: MCP Tools (CRUD Operations)

### Step 7.1: READ Tool - Get Inventory Status

**Why:** Allow Claude to query inventory.

**Add to main.py:**

```python
@mcp.tool()
async def get_inventory_status(
    product_name: Optional[str] = Field(None, description="The name or partial name of the product to search for."), 
) -> List[Product]:
    """READ operation: Retrieves inventory status for all products or a specific product."""
    matches = fuzzy_match_product(product_name)

    if not matches and product_name:
        raise ValueError(f"No products found matching '{product_name}'.")
        
    return matches
```

**Explanation:**

- `@mcp.tool()`: Decorator that registers function as MCP tool
- `async def`: Async function (required by MCP)
- `Optional[str]`: Parameter can be None (get all products)
- `Field()`: Adds description for Claude to understand the tool
- `raise ValueError`: Error handling (MCP converts to proper error response)

### Step 7.2: CREATE Tool - Add New Product

**Why:** Allow Claude to add products to inventory.

**Add to main.py:**

```python
@mcp.tool()
async def add_new_product(
    name: str = Field(..., description="The name of the product to add."),
    initial_quantity: int = Field(..., description="The initial stock quantity."),
    unit_price: float = Field(..., description="The price per unit."),
) -> Product:
    """CREATE operation: Adds a new product to the inventory."""
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
```

**Explanation:**

- `uuid.uuid4()`: Generate unique ID
- `.split('-')[0]`: Take first segment of UUID
- `.upper()`: Convert to uppercase (e.g., "P-80562C3C")
- `save_inventory()`: Write to disk immediately

### Step 7.3: UPDATE Tool - Adjust Stock

**Why:** Allow Claude to modify stock quantities.

**Add to main.py:**

```python
@mcp.tool()
async def adjust_stock_quantity(
    product_name: str = Field(..., description="The name of the product to adjust."),
    quantity_change: int = Field(..., description="Positive number to increase stock, negative number to decrease stock."),
) -> Product:
    """UPDATE operation: Adjusts the stock quantity of an existing product."""
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
```

**Explanation:**

- Ambiguity check: Ensure only one product matches
- Business rule: Prevent negative stock (data validation)
- Update in-place: Modify existing product in database

### Step 7.4: DELETE Tool - Remove Product

**Why:** Allow Claude to remove products.

**Add to main.py:**

```python
@mcp.tool()
async def remove_product(
    product_name: str = Field(..., description="The name of the product to remove."),
):
    """DELETE operation: Permanently removes a product from the inventory."""
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
```

**Explanation:**

- Same ambiguity check as UPDATE tool
- `del INVENTORY_DB[original_id]`: Remove from dictionary
- Return success message for confirmation

---

## Phase 8: REST API Server Setup

### Step 8.1: Initialize FastAPI Application

**Why:** Create REST API endpoints for HTTP access (alternative to MCP).

**Add to main.py:**

```python
app = FastAPI(
    title="Inventory Manager API",
    description="REST API for managing inventory with full CRUD operations",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI documentation
    redoc_url="/redoc"  # ReDoc documentation
)
```

**Explanation:**

- `FastAPI()`: Main application instance
- `docs_url`: Auto-generated API docs at http://localhost:8000/docs
- `redoc_url`: Alternative documentation at http://localhost:8000/redoc

### Step 8.2: Optional Security Configuration

**Why:** Add API key authentication (optional, can be removed if not needed).

**Add to main.py:**

```python
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)
SECRET_API_KEY = os.environ.get("MCP_API_KEY", "super-secret-mcp-key")

def get_api_key(api_key: str = Security(api_key_header)):
    """Validates the API key from request headers."""
    if api_key == SECRET_API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )
```

**Note:** This is currently not used in endpoints but available for future use.

---

## Phase 9: REST API Endpoints

### Step 9.1: GET - List All Products or Search

**Why:** Retrieve products via HTTP GET request.

**Add to main.py:**

```python
@app.get("/api/products", 
         response_model=List[Product],
         summary="Get all products or search by name",
         tags=["Products"])
async def get_products(
    name: Optional[str] = Query(None, description="Filter products by name (fuzzy match)")
):
    """Retrieve all products or search for products by name."""
    load_inventory()  # Reload from disk to sync with MCP changes
    matches = fuzzy_match_product(name)
    
    if not matches and name:
        raise HTTPException(
            status_code=404,
            detail=f"No products found matching '{name}'."
        )
    
    return matches
```

**Explanation:**

- `@app.get()`: HTTP GET endpoint decorator
- `Query()`: Extract query parameter from URL (?name=beer)
- `load_inventory()`: Sync with any MCP changes
- `HTTPException`: Return proper HTTP error codes

### Step 9.2: GET - Get Product by ID

**Why:** Retrieve specific product using exact ID.

**Add to main.py:**

```python
@app.get("/api/products/{product_id}",
         response_model=Product,
         summary="Get product by ID",
         tags=["Products"])
async def get_product_by_id(product_id: str = Path(..., description="Product ID")):
    """Retrieve a specific product by its unique product ID."""
    load_inventory()
    if product_id not in INVENTORY_DB:
        raise HTTPException(
            status_code=404,
            detail=f"Product with ID '{product_id}' not found."
        )
    return INVENTORY_DB[product_id]
```

**Explanation:**

- `{product_id}`: Path parameter in URL (/api/products/P-001)
- `Path(...)`: Required path parameter

### Step 9.3: POST - Create New Product

**Why:** Add products via HTTP POST request.

**Add to main.py:**

```python
@app.post("/api/products",
          response_model=Product,
          status_code=status.HTTP_201_CREATED,
          summary="Add a new product",
          tags=["Products"])
async def create_product(product: NewProductRequest):
    """CREATE operation: Add a new product to the inventory."""
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
```

**Explanation:**

- `@app.post()`: HTTP POST endpoint
- `status_code=201`: Created status code
- `product: NewProductRequest`: Request body automatically validated by Pydantic

### Step 9.4: PATCH - Adjust Stock Quantity

**Why:** Update stock via HTTP PATCH request.

**Add to main.py:**

```python
@app.patch("/api/products/{product_name}/stock",
           response_model=Product,
           summary="Adjust product stock quantity",
           tags=["Products"])
async def adjust_stock(
    product_name: str = Path(..., description="Product name to adjust"),
    quantity_change: int = Query(..., description="Positive to increase, negative to decrease")
):
    """UPDATE operation: Adjust the stock quantity of a product."""
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
```

**Explanation:**

- `@app.patch()`: HTTP PATCH for partial updates
- Same logic as MCP tool but returns HTTPException instead of ValueError

### Step 9.5: DELETE - Remove Product

**Why:** Delete products via HTTP DELETE request.

**Add to main.py:**

```python
@app.delete("/api/products/{product_name}",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Remove a product",
            tags=["Products"])
async def delete_product(
    product_name: str = Path(..., description="Product name to remove")
):
    """DELETE operation: Permanently remove a product from inventory."""
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
    
    return None  # 204 No Content - no response body
```

**Explanation:**

- `status_code=204`: No Content (standard for DELETE)
- Returns `None` (no response body)

### Step 9.6: GET - Health Check Endpoint

**Why:** Verify API is running (useful for monitoring).

**Add to main.py:**

```python
@app.get("/api/health",
         summary="Health check endpoint",
         tags=["Health"])
async def health_check():
    """Health check endpoint to verify the API is running."""
    return {
        "status": "healthy",
        "total_products": len(INVENTORY_DB)
    }
```

---

## Phase 10: Server Execution

### Step 10.1: Main Execution Block

**Why:** Allow script to run in two modes (MCP or HTTP).

**Add to main.py:**

```python
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        # HTTP REST API mode
        print("Starting Inventory Manager REST API server...")
        print("Swagger docs available at: http://localhost:8000/docs")
        print("API available at: http://localhost:8000/api")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # MCP mode (default): Run as stdio server for Claude Desktop
        mcp.run(transport="stdio")
```

**Explanation:**

- `sys.argv`: Command-line arguments
- `uvicorn.run()`: Start FastAPI server
- `mcp.run(transport="stdio")`: Start MCP server (communicates via stdin/stdout)

---

## Phase 11: Testing and Running

### Step 11.1: Configure Claude Desktop for MCP

**Why:** Connect your MCP server to Claude Desktop so Claude can use your inventory tools.

**Action:**

1. **Locate Claude Desktop Config File:**

   The config file location depends on your operating system:
   
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
     - Full path: `C:\Users\YOUR_USERNAME\AppData\Roaming\Claude\claude_desktop_config.json`
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux:** `~/.config/Claude/claude_desktop_config.json`

2. **Open the Config File:**

   - If the file doesn't exist, create it as a new JSON file
   - Use a text editor (VS Code, Notepad++, etc.)

3. **Add Your MCP Server Configuration:**

   Add the following JSON structure to the config file. Replace the path with your actual `main.py` location:

   **For Windows (using system Python):**
   ```json
   {
     "mcpServers": {
       "inventory-manager": {
         "command": "python",
         "args": [
           "C:\\Users\\YOUR_USERNAME\\path\\to\\inventory-mcp\\main.py"
         ],
         "env": {
           "MCP_API_KEY": "super-secret-mcp-key"
         }
       }
     }
   }
   ```

   **For Windows (using uv's Python):**
   ```json
   {
     "mcpServers": {
       "inventory-manager": {
         "command": ".venv\\Scripts\\python.exe",
         "args": [
           "main.py"
         ],
         "cwd": "C:\\Users\\YOUR_USERNAME\\path\\to\\inventory-mcp",
         "env": {
           "MCP_API_KEY": "super-secret-mcp-key"
         }
       }
     }
   }
   ```

   **For macOS/Linux (using system Python):**
   ```json
   {
     "mcpServers": {
       "inventory-manager": {
         "command": "python",
         "args": [
           "/full/path/to/inventory-mcp/main.py"
         ],
         "env": {
           "MCP_API_KEY": "super-secret-mcp-key"
         }
       }
     }
   }
   ```

   **For macOS/Linux (using uv's Python):**
   ```json
   {
     "mcpServers": {
       "inventory-manager": {
         "command": ".venv/bin/python",
         "args": [
           "main.py"
         ],
         "cwd": "/full/path/to/inventory-mcp",
         "env": {
           "MCP_API_KEY": "super-secret-mcp-key"
         }
       }
     }
   }
   ```

   **Important Notes:**
   - Replace `YOUR_USERNAME` and paths with your actual values
   - Use double backslashes (`\\`) in Windows paths
   - If you already have other MCP servers configured, add `"inventory-manager"` to the existing `mcpServers` object (don't replace it)
   - The `env` section is optional but useful if you want to use the API key feature

4. **Save and Restart Claude Desktop:**

   - Save the config file
   - Completely close and restart Claude Desktop
   - The MCP server should now be available

### Step 11.2: Test MCP Mode

**Why:** Verify MCP server works with Claude Desktop.

**Action:**

1. **Verify Connection:**

   - Open Claude Desktop
   - The inventory manager tools should appear in Claude's available tools
   - Try asking Claude: "What products are in the inventory?" or "Add a new product called 'Test Item' with quantity 10 and price 5.99"

2. **Run MCP server manually (for testing):**
   ```bash
   python main.py
   ```
   - Server runs in stdio mode (waits for input)
   - Claude Desktop connects automatically when configured

### Step 11.2: Test REST API Mode

**Why:** Verify REST API endpoints work.

**Action:**

1. **Start HTTP server:**
   ```bash
   python main.py http
   ```

2. **Open browser:**

   - Visit: http://localhost:8000/docs
   - Interactive API documentation (Swagger UI)

3. **Test endpoints:**

   - Click "Try it out" on any endpoint
   - Enter parameters
   - Click "Execute"

### Step 11.3: Test with curl (Command Line)

**Why:** Verify API works from terminal.

**Examples:**

```bash
# Get all products
curl http://localhost:8000/api/products

# Search for product
curl "http://localhost:8000/api/products?name=beer"

# Create product
curl -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Product", "initial_quantity": 10, "unit_price": 5.99}'

# Adjust stock
curl -X PATCH "http://localhost:8000/api/products/Test%20Product/stock?quantity_change=-2"

# Delete product
curl -X DELETE "http://localhost:8000/api/products/Test%20Product"
```


---

## Phase 12: Project Structure Summary

### Final File Structure

```
inventory-mcp/
├── main.py              # Main server code (all code above)
├── pyproject.toml        # Dependencies and project config
├── uv.lock              # Locked dependency versions
├── inventory.json       # Data file (created automatically)
├── README.md            # Project documentation
└── .venv/               # Virtual environment (created by uv)
```

### Key Files Explained

- **main.py**: Complete server implementation (~538 lines)
- **pyproject.toml**: Dependency management
- **inventory.json**: Persistent data storage
- **uv.lock**: Ensures reproducible builds

---

## Phase 13: Next Steps and Enhancements

### Potential Improvements

1. **Database Integration:**

   - Replace JSON file with SQLite/PostgreSQL
   - Use SQLAlchemy ORM

2. **Authentication:**

   - Implement JWT tokens
   - Add user management

3. **Advanced Features:**

   - Product categories
   - Inventory history/audit logs
   - Low stock alerts
   - Bulk operations

4. **Testing:**

   - Add unit tests with pytest
   - Add integration tests
   - Test MCP tools

5. **Deployment:**

   - Docker containerization
   - Deploy to cloud (AWS, GCP, Azure)
   - Add CI/CD pipeline

---

## Troubleshooting

### Common Issues

1. **Import Errors:**

   - Ensure virtual environment is activated
   - Run `uv sync` to install dependencies

2. **Port Already in Use:**

   - Change port in `uvicorn.run(app, port=8001)`
   - Or kill process using port 8000

3. **File Permission Errors:**

   - Check write permissions for inventory.json
   - Ensure script directory is writable

4. **MCP Connection Issues:**

   - Verify Claude Desktop configuration
   - Check stdio transport is correct

---

## Conclusion

You now have a complete, production-ready MCP server with REST API capabilities! The server supports:

- ✅ Full CRUD operations (Create, Read, Update, Delete)
- ✅ MCP integration for Claude Desktop
- ✅ REST API with automatic documentation
- ✅ Persistent data storage
- ✅ Fuzzy product search
- ✅ Input validation and error handling

**Next:** Start building your own enhancements and customizations!