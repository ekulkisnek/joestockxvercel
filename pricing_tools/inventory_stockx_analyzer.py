#!/usr/bin/env python3
"""
📊 Inventory StockX Analyzer
Flexible tool to analyze any inventory CSV format and get StockX pricing data
"""

import csv
import json
import re
import time
import sys
import os
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    try:
        import pytz
        ZoneInfo = None
    except ImportError:
        pytz = None
        ZoneInfo = None

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure immediate output flushing for real-time web interface progress
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# Import our existing StockX client
from smart_stockx_client import SmartStockXClient
from sales_volume_analyzer import SalesVolumeAnalyzer

class InventoryItem:
    """Represents a single inventory item"""
    def __init__(self, shoe_name: str, size: str = None, price: str = None, condition: str = None, original_data: Dict = None):
        self.shoe_name = shoe_name.strip() if shoe_name else ""
        self.size = size.strip() if size else ""
        self.price = price.strip() if price else ""
        self.condition = condition.strip() if condition else ""
        
        # Store original CSV data to preserve all columns
        self.original_data = original_data or {}
        
        # Add quantity tracking
        self.quantity = 1  # Default quantity
        
        # Extract and append condition notes from shoe name
        self.condition_notes = self._extract_condition_notes(self.shoe_name)
        if self.condition_notes and self.condition:
            self.condition = f"{self.condition} {self.condition_notes}".strip()
        elif self.condition_notes:
            self.condition = self.condition_notes

        # StockX data
        self.stockx_bid = None
        self.stockx_ask = None
        # Alias pricing data
        self.lowest_consigned = None
        self.last_consigned_price = None
        self.last_consigned_date = None
        self.lowest_with_you = None
        self.last_with_you_price = None
        self.last_with_you_date = None
        self.consignment_price = None
        self.ship_to_verify_price = None
        # StockX metadata
        self.stockx_sku = None
        self.stockx_url = None
        self.stockx_size = None
        self.stockx_shoe_name = None

        # Profit calculations
        self.bid_profit = None
        self.ask_profit = None
        
        # Volume and pricing data
        self.weekly_volume = None  # Last 7 days count (current)
        self.weekly_volume_prev = None  # Previous estimate (velocity*7)
        self.price_offer = None
        self.offer_reasoning = None
    
    def _extract_condition_notes(self, shoe_name: str) -> str:
        """Extract condition notes from shoe name (DS, VNDS, no box, etc.)"""
        if not shoe_name:
            return ""
        
        condition_patterns = [
            r'\(DS\)',
            r'\(VNDS\)',
            r'\(no box\)',
            r'\(missing laces\)',
            r'\(slight markings[^)]*\)',
            r'\(worn\)',
            r'\(used\)',
            r'\(new\)',
            r'\(deadstock\)',
        ]
        
        extracted_notes = []
        for pattern in condition_patterns:
            matches = re.findall(pattern, shoe_name, re.IGNORECASE)
            extracted_notes.extend(matches)
        
        return " ".join(extracted_notes).strip()

class InventoryStockXAnalyzer:
    def __init__(self):
        """Initialize with StockX client"""
        # Initialize client without auto-authentication first
        self.client = SmartStockXClient(auto_authenticate=False)
        self.processed_count = 0
        self.matches_found = 0
        self.cache = {}
        
        # Initialize volume analyzer for weekly volume calculations
        self.volume_analyzer = SalesVolumeAnalyzer()
        
        # Setup robust token file handling for different deployment environments
        self._setup_authentication()

    def _setup_authentication(self):
        """Setup robust authentication handling for different deployment environments"""
        # List of possible token file locations to try
        possible_token_files = [
            'tokens_full_scope.json',                    # Same directory
            '../tokens_full_scope.json',                 # Parent directory  
            '../../tokens_full_scope.json',              # Grandparent directory
            os.path.expanduser('~/tokens_full_scope.json'), # Home directory
            '/tmp/tokens_full_scope.json',               # Temp directory
        ]
        
        # Try to find existing token file
        token_file_found = None
        for token_file in possible_token_files:
            if os.path.exists(token_file):
                token_file_found = token_file
                print(f"📋 Found token file: {token_file}")
                break
        
        if token_file_found:
            self.client.token_file = token_file_found
            try:
                self.client._ensure_authentication()
                print("✅ Authentication successful")
                return
            except Exception as e:
                print(f"⚠️ Token file found but authentication failed: {e}")
        else:
            print("⚠️ No existing token file found")
        
        # If no token file found or authentication failed, try to authenticate fresh
        print("🔄 Attempting fresh authentication...")
        try:
            # Set a default token file location
            self.client.token_file = 'tokens_full_scope.json'
            self.client._ensure_authentication()
            print("✅ Fresh authentication successful")
        except Exception as e:
            print(f"❌ Fresh authentication failed: {e}")
            print("💡 Please ensure you have valid StockX credentials configured")
            # Don't raise the exception - let the processing continue and handle auth errors per request

    def _convert_date_to_days_ago(self, date_string: str) -> str:
        """Convert ISO date string to number of days ago"""
        if not date_string:
            return ""
        
        try:
            # Parse the ISO date string (e.g. "2025-07-18T17:37:53.102Z")
            if date_string.endswith('Z'):
                date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            else:
                date_obj = datetime.fromisoformat(date_string)
            
            # Convert to US Central time
            central_now = None
            date_central = None
            
            if ZoneInfo:
                # Use zoneinfo (Python 3.9+)
                central_tz = ZoneInfo('US/Central')
                central_now = datetime.now(central_tz)
                if date_obj.tzinfo:
                    date_central = date_obj.astimezone(central_tz)
                else:
                    date_central = date_obj
            elif pytz:
                # Use pytz fallback
                central_tz = pytz.timezone('US/Central')
                central_now = datetime.now(central_tz)
                if date_obj.tzinfo:
                    date_central = date_obj.astimezone(central_tz)
                else:
                    date_central = date_obj
            else:
                # No timezone library available
                central_now = datetime.now()
                date_central = date_obj
            
            # Calculate days difference from today in Central time
            if central_now and date_central:
                days_diff = (central_now.date() - date_central.date()).days
            else:
                # Fallback calculation
                today = datetime.now(date_obj.tzinfo) if date_obj.tzinfo else datetime.now()
                days_diff = (today - date_obj).days
            
            # Return just the number
            return str(days_diff)
                
        except (ValueError, TypeError):
            return ""

    def parse_csv_flexible(self, csv_file: str) -> List[InventoryItem]:
        """Parse CSV file while preserving all original columns"""
        items = []

        # Read and parse as CSV
        with open(csv_file, 'r', encoding='utf-8') as file:
            lines = list(csv.reader(file))

        if not lines:
            return items

        # Store header information for column preservation
        self.original_headers = lines[0] if lines else []
        self.has_headers = self._looks_like_header_row(self.original_headers)
        
        start_row = 1 if self.has_headers else 0
        
        # Detect column mappings from headers or content analysis
        shoe_col, size_col, price_col, condition_col = self._detect_column_mappings(lines)
        
        for i in range(start_row, len(lines)):
            row = lines[i]
            if not row or all(not cell.strip() for cell in row):
                continue

            # Create dictionary of original data for preservation
            original_data = {}
            for j, header in enumerate(self.original_headers):
                if j < len(row):
                    original_data[header] = row[j]

            # Extract the core data we need for processing
            shoe_name = row[shoe_col] if shoe_col is not None and shoe_col < len(row) else ""
            size = row[size_col] if size_col is not None and size_col < len(row) else ""
            price = row[price_col] if price_col is not None and price_col < len(row) else ""
            condition = row[condition_col] if condition_col is not None and condition_col < len(row) else ""

            if shoe_name.strip():  # Only process if we have a shoe name
                item = InventoryItem(shoe_name, size, price, condition, original_data)
                items.append(item)

        return items

    def _detect_column_mappings(self, lines: List[List[str]]) -> Tuple[int, int, int, int]:
        """Detect which columns contain shoe name, size, price, and condition"""
        if not lines:
            return None, None, None, None
            
        headers = lines[0] if self.has_headers else []
        
        # Initialize column indices
        shoe_col = None
        size_col = None  
        price_col = None
        condition_col = None
        
        # Try to detect from headers first
        if self.has_headers:
            for i, header in enumerate(headers):
                header_lower = header.lower().strip()
                
                if shoe_col is None and any(word in header_lower for word in ['shoe', 'name', 'product', 'item']):
                    shoe_col = i
                elif size_col is None and 'size' in header_lower:
                    size_col = i  
                elif price_col is None and any(word in header_lower for word in ['price', 'cost', 'amount']):
                    price_col = i
                elif condition_col is None and any(word in header_lower for word in ['condition', 'state', 'quality']):
                    condition_col = i
        
        # Fallback: analyze content to detect columns
        if shoe_col is None or size_col is None:
            # Analyze first few data rows to detect patterns
            sample_rows = lines[1:min(6, len(lines))] if self.has_headers else lines[:5]
            
            for row in sample_rows:
                if not row:
                    continue
                    
                for i, cell in enumerate(row):
                    cell = cell.strip()
                    if not cell:
                        continue
                        
                    # Detect shoe name column (usually longest text, has brand names)
                    if shoe_col is None and len(cell) > 10 and any(brand in cell.upper() for brand in ['JORDAN', 'NIKE', 'ADIDAS', 'YEEZY']):
                        shoe_col = i
                    
                    # Detect size column
                    elif size_col is None and self._looks_like_size(cell):
                        size_col = i
                        
                    # Detect price column  
                    elif price_col is None and self._looks_like_price(cell):
                        price_col = i
                        
                    # Detect condition column
                    elif condition_col is None and self._looks_like_condition(cell):
                        condition_col = i
        
        # Final fallback: use positional defaults
        if shoe_col is None:
            shoe_col = 0  # First column is usually shoe name
        
        return shoe_col, size_col, price_col, condition_col

    def parse_pasted_list(self, text: str) -> List[InventoryItem]:
        """Parse pasted list format - handles multiple inventory formats flexibly"""
        import re
        items = []
        
        # Clean the text
        text = text.strip()
        
        # Remove header if present
        text = re.sub(r'^SHOE LIST[^)]*\)', '', text, flags=re.IGNORECASE).strip()
        
        # Split into individual lines (handles both multi-line and properly formatted lists)
        lines = []
        if '\n' in text:
            # Multi-line format - simple line splitting
            lines = [line.strip() for line in text.split('\n') if line.strip()]
        else:
            # Single line format - try to split intelligently
            # For now, assume single line means it's already one item
            lines = [text.strip()] if text.strip() else []
        
        print(f"📋 Split into {len(lines)} potential shoe entries")
        
        for i, line in enumerate(lines):
            if not line or len(line) < 5:  # Skip very short lines
                continue
            
            # Skip header lines
            if any(skip in line.upper() for skip in ['SHOE LIST', 'TAKE ALL ONLY', 'QUANTITY', 'SIZE']):
                continue
            
            print(f"   Processing line {i+1}: {line[:60]}...")
            
            # Try to parse the line using multiple strategies
            parsed_item = self._parse_inventory_line(line)
            
            if parsed_item:
                items.extend(parsed_item)  # _parse_inventory_line returns a list
            else:
                print(f"   ⚠️ Could not parse line: {line[:50]}...")
        
        return items
    
    def _parse_inventory_line(self, line: str) -> List[InventoryItem]:
        """Parse a single inventory line - returns list of items (for quantity support)"""
        # Strategy 1: Try SKU-based format (e.g., "DQ8426 067 - sz12 x2")
        sku_items = self._try_parse_sku_format(line)
        if sku_items:
            return sku_items
        
        # Strategy 2: Try traditional shoe name format with various price patterns
        name_items = self._try_parse_name_format(line)
        if name_items:
            return name_items
        
        return []
    
    def _try_parse_sku_format(self, line: str) -> List[InventoryItem]:
        """Try to parse SKU-based format like 'DQ8426 067 - sz12 x2'"""
        import re
        
        # SKU patterns: alphanumeric codes with possible spaces/dashes
        # Look for patterns like: DQ8426 067, GC1906ER, FB9107 131, etc.
        sku_pattern = r'^([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)*)\s*-?\s*'
        
        match = re.match(sku_pattern, line)
        if not match:
            return []
        
        potential_sku = match.group(1).strip()
        
        # Check if this looks like a SKU (not a shoe name)
        # SKUs are typically short alphanumeric codes, not long descriptive names
        if (len(potential_sku) < 4 or len(potential_sku) > 20 or 
            any(word in potential_sku.lower() for word in ['jordan', 'nike', 'adidas', 'yeezy', 'dunk'])):
            return []
        
        print(f"   🔍 Detected potential SKU: {potential_sku}")
        
        # Extract the rest of the line after the SKU
        remainder = line[len(match.group(0)):].strip()
        
        # Look for size and quantity information
        size_info = self._extract_size_and_quantity(remainder)
        
        if not size_info:
            print(f"   ⚠️ No size found for SKU: {potential_sku}")
            return []
        
        # Create items for each size/quantity combination
        items = []
        for size, quantity in size_info:
            for q in range(quantity):
                item = InventoryItem(
                    shoe_name=potential_sku,  # Use SKU as shoe name for searching
                    size=size,
                    price="",  # SKU lists usually don't have prices
                    condition="Brand New"  # Default condition
                )
                # Mark this as a SKU search for later processing
                item.is_sku_search = True
                # Track original quantity for this size
                item.quantity = quantity
                items.append(item)
        
        print(f"   ✅ Parsed SKU: {potential_sku} - {len(items)} items")
        return items
    
    def _try_parse_name_format(self, line: str) -> List[InventoryItem]:
        """Try to parse traditional shoe name format with price"""
        import re
        
        # Look for price patterns (multiple formats)
        price_patterns = [
            r'-\$(\d+(?:\.\d{2})?)',           # -$300
            r'ALL-\$(\d+(?:\.\d{2})?)',        # ALL-$300  
            r'ALL\s+\$(\d+(?:\.\d{2})?)',      # ALL $240
            r'\$(\d+(?:\.\d{2})?)',            # $300
            r'\(\$(\d+(?:\.\d{2})?)\)',        # ($300)
        ]
        
        price = None
        price_match = None
        
        for pattern in price_patterns:
            match = re.search(pattern, line)
            if match:
                price = match.group(1)
                price_match = match
                break
        
        if not price:
            print(f"   ⚠️ No price found in: {line[:50]}...")
            return []
        
        # Remove price and any notes after it
        line_without_price = line[:price_match.start()].strip()
        
        # Look for size information with flexible patterns
        size_info = self._extract_size_and_quantity(line)
        
        if not size_info:
            print(f"   ⚠️ No size found in: {line[:50]}...")
            return []
        
        # Extract shoe name (everything before size information)
        shoe_name = self._extract_shoe_name(line_without_price)
        
        if not shoe_name:
            print(f"   ⚠️ No shoe name found in: {line[:50]}...")
            return []
        
        # Create items for each size/quantity combination
        items = []
        for size, quantity in size_info:
            # Determine condition based on context
            condition = self._determine_condition(line)
            
            for q in range(quantity):
                item = InventoryItem(
                    shoe_name=shoe_name,
                    size=size,
                    price=price,
                    condition=condition
                )
                # Track original quantity for this size
                item.quantity = quantity
                items.append(item)
        
        print(f"   ✅ Parsed: '{shoe_name}' - {len(items)} items - ${price}")
        return items
    
    def _extract_size_and_quantity(self, text: str) -> List[Tuple[str, int]]:
        """Extract size and quantity information from text - handles multiple formats"""
        import re
        
        size_info = []
        
        # Size patterns to look for (in order of specificity)
        # Start with most specific patterns first
        size_patterns = [
            # Format: sz12 x2, sz5.5 x2 (with quantity)
            r'sz(\d+(?:\.\d+)?[YyWwCc]?)\s*x\s*(\d+)',
            # Format: - sz12 x2, - sz5.5 x2 (with quantity)
            r'-\s*sz(\d+(?:\.\d+)?[YyWwCc]?)\s*x\s*(\d+)',
            # Format: sz12, sz5.5 (without quantity)
            r'sz(\d+(?:\.\d+)?[YyWwCc]?)(?!\s*x)',
            # Format: - sz12, - sz5.5 (without quantity)  
            r'-\s*sz(\d+(?:\.\d+)?[YyWwCc]?)(?!\s*x)',
        ]
        
        # Try each pattern until we find a match
        for pattern in size_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            if matches:
                for match in matches:
                    if isinstance(match, tuple) and len(match) == 2:
                        size_str = match[0].strip()
                        quantity_str = match[1].strip()
                    elif isinstance(match, tuple) and len(match) == 1:
                        size_str = match[0].strip()
                        quantity_str = "1"
                    else:
                        size_str = str(match).strip()
                        quantity_str = "1"
                    
                    try:
                        quantity = int(quantity_str) if quantity_str else 1
                    except ValueError:
                        quantity = 1
                    
                    # Clean up size format
                    size = self._normalize_extracted_size(size_str)
                    if size:
                        size_info.append((size, quantity))
                
                # If we found matches with this pattern, don't try other patterns
                if size_info:
                    break
        
        # If no sz pattern found, try to find sizes in the format "5w", "10m", etc.
        if not size_info:
            # Look for sizes with shoe size suffixes - but be more specific
            size_matches = re.findall(r'\b(\d+(?:\.\d+)?[YyWwMmCc])\b', text, re.IGNORECASE)
            for size_str in size_matches:
                size = self._normalize_extracted_size(size_str)
                if size and self._is_reasonable_shoe_size(size):
                    size_info.append((size, 1))
                    break  # Take the first reasonable size
        
        return size_info
    
    def _normalize_extracted_size(self, size_str: str) -> str:
        """Normalize extracted size string"""
        if not size_str:
            return ""
        
        # Remove any whitespace
        size_clean = size_str.strip()
        
        # Standardize size suffixes
        size_clean = re.sub(r'[Yy]$', 'Y', size_clean)  # Youth
        size_clean = re.sub(r'[Ww]$', 'W', size_clean)  # Women
        size_clean = re.sub(r'[Cc]$', 'C', size_clean)  # Child
        size_clean = re.sub(r'[Mm]$', '', size_clean)   # Men (remove M)
        
        return size_clean
    
    def _is_reasonable_shoe_size(self, size_str: str) -> bool:
        """Check if a size string represents a reasonable shoe size"""
        try:
            # Extract numeric part
            numeric_part = re.sub(r'[YyWwMmCc]', '', size_str)
            size_num = float(numeric_part)
            # Reasonable shoe size range
            return 3 <= size_num <= 18
        except (ValueError, TypeError):
            return False
    
    def _extract_shoe_name(self, text: str) -> str:
        """Extract shoe name from text, removing size and condition info"""
        import re
        
        # Remove common size patterns from the text - be more conservative
        text_clean = text
        
        # First, remove explicit size patterns like "sz12" or "- sz12"
        size_removal_patterns = [
            r'\s*-?\s*sz\d+(?:\.\d+)?[YyWwCc]?.*$',     # Remove sz12 and everything after
            r'\s*-?\s*size\s+\d+.*$',                   # Remove "size 12" and after
        ]
        
        for pattern in size_removal_patterns:
            text_clean = re.sub(pattern, '', text_clean, flags=re.IGNORECASE).strip()
        
        # Then remove size patterns that are clearly at the end with size suffixes
        # Be more conservative - only remove if it's clearly a size at the end
        size_suffix_patterns = [
            r'\s+(\d+(?:\.\d+)?[YyWwMmCc])\s*$',        # Remove "5w" or "10m" at the end
        ]
        
        for pattern in size_suffix_patterns:
            match = re.search(pattern, text_clean)
            if match:
                potential_size = match.group(1)
                if self._is_reasonable_shoe_size(potential_size):
                    text_clean = re.sub(pattern, '', text_clean).strip()
        
        # Remove common condition/quality indicators from end - but be more specific
        condition_patterns = [
            r'\s+DS\s+OG\s+ALL\s*$',         # "DS OG ALL" at end
            r'\s+VNDS\s+OG\s+ALL\s*$',       # "VNDS OG ALL" at end  
            r'\s+DS\s*$',                    # "DS" at end
            r'\s+VNDS\s*$',                  # "VNDS" at end
            r'\s+NB\s*$',                    # "NB" (no box) at end
            r'\s+OG\s+ALL\s*$',              # "OG ALL" at end
        ]
        
        for pattern in condition_patterns:
            text_clean = re.sub(pattern, '', text_clean, flags=re.IGNORECASE).strip()
        
        # Remove trailing dashes and spaces
        text_clean = re.sub(r'\s*-\s*$', '', text_clean).strip()
        
        return text_clean
    
    def _determine_condition(self, line: str) -> str:
        """Determine condition from line text"""
        line_lower = line.lower()
        
        # Check for specific condition indicators
        if 'vnds' in line_lower:
            return "Very Near Deadstock"
        elif 'ds' in line_lower:
            return "Brand New"  # Deadstock
        elif 'used' in line_lower:
            return "Used"
        elif 'worn' in line_lower:
            return "Used"
        elif 'nb' in line_lower or 'no box' in line_lower:
            return "Brand New (No Box)"  # No box but still new
        else:
            return "Brand New"  # Default assumption

    def _is_complete_item_row(self, row: List[str]) -> bool:
        """Check if this row contains a complete item (Format 1)"""
        if len(row) < 2:
            return False

        first_cell = row[0].strip() if row[0] else ""
        if not self._looks_like_shoe_name(first_cell):
            return False

        # Look for size in second column (like M10, 5Y, W11, etc.)
        second_cell = row[1].strip() if len(row) > 1 and row[1] else ""
        if self._looks_like_size(second_cell):
            return True

        # Look for size anywhere in first few columns
        for j in range(1, min(4, len(row))):
            cell = row[j].strip() if row[j] else ""
            if self._looks_like_size(cell):
                return True

        return False

    def _looks_like_condition(self, text: str) -> bool:
        """Check if text looks like a condition"""
        if not text:
            return False

        condition_keywords = [
            'brand new', 'used', 'vnds', 'og all', 'no box', 'damaged box', 
            'rep box', 'no lid', 'special box', 'missing'
        ]

        text_lower = text.lower()
        return any(keyword in text_lower for keyword in condition_keywords)

    def _looks_like_shoe_name(self, text: str) -> bool:
        """Check if text looks like a shoe name"""
        if not text or len(text) < 3:
            return False

        brands = ['jordan', 'nike', 'adidas', 'yeezy', 'dunk', 'air', 'sb']
        text_lower = text.lower()

        return any(brand in text_lower for brand in brands)

    def _looks_like_size(self, text: str) -> bool:
        """Check if text looks like a shoe size"""
        if not text:
            return False

        text_clean = text.strip().upper()

        size_patterns = [
            r'^\d+\.?\d*[YCW]?$',           # 10, 10.5, 10Y, 10C, 10W
            r'^[MW]\d+\.?\d*$',             # M10, W10, M10.5
            r'^\d+\.?\d*\s*-\s*\d+$',       # 10 - 12, size ranges
            r'^\d+Y$',                      # 5Y (youth)
            r'^\d+C$',                      # 10C (child)
            r'^\d+W$',                      # 10W (women)
        ]

        for pattern in size_patterns:
            if re.match(pattern, text_clean):
                return True

        return False

    def _looks_like_price(self, text: str) -> bool:
        """Check if text looks like a price"""
        if not text:
            return False

        cleaned = re.sub(r'[$,]', '', text.strip())

        try:
            price = float(cleaned)
            return 10 <= price <= 10000
        except ValueError:
            return False

    def _parse_price(self, price_str: str) -> Optional[float]:
        """Parse price string to float"""
        if not price_str:
            return None

        try:
            # Remove currency symbols and whitespace
            clean_price = re.sub(r'[$,]', '', price_str.strip())
            return float(clean_price)
        except (ValueError, AttributeError):
            return None

    def normalize_size(self, size: str) -> Tuple[str, str]:
        """Normalize size format and determine category"""
        if not size:
            return "", "men"

        size_clean = size.strip().upper()

        # Handle size ranges
        if ' - ' in size_clean:
            size_clean = size_clean.split(' - ')[0].strip()

        # Handle different size formats with better recognition
        # Youth/Grade School sizes: Y, y (case insensitive)
        if size_clean.endswith('Y') or re.match(r'^\d+\.?\d*Y$', size_clean):
            numeric_size = re.sub(r'[Y]', '', size_clean)
            return f"{numeric_size}Y", "gs"  # Grade School
        
        # Preschool sizes: C, c (case insensitive) 
        elif size_clean.endswith('C') or re.match(r'^\d+\.?\d*C$', size_clean):
            numeric_size = re.sub(r'[C]', '', size_clean)
            return f"{numeric_size}C", "ps"  # Preschool
        
        # Women's sizes: W, w (case insensitive) - can be prefix or suffix
        elif (size_clean.endswith('W') or size_clean.startswith('W') or 
              re.match(r'^\d+\.?\d*W$', size_clean)):
            numeric_size = re.sub(r'[WM]', '', size_clean)
            return f"{numeric_size}W", "women"
        
        # Men's sizes: M prefix or just numeric
        elif size_clean.startswith('M'):
            numeric_size = re.sub(r'[WM]', '', size_clean)
            return numeric_size, "men"
        
        # Default to men's if just numeric
        else:
            return size_clean, "men"

    def clean_shoe_name_for_search(self, shoe_name: str) -> str:
        """Clean shoe name for StockX search while preserving important details"""
        cleaned = shoe_name.strip()

        # Only remove generic condition/quality notes, preserve important details
        patterns_to_remove = [
            r'\s*\(slight markings[^)]*\)$',  # Remove condition notes
            r'\s*\(no box\)$',                # Remove packaging notes
            r'\s*\(VNDS\)$',                  # Remove condition abbreviations
            r'\s*\(DS\)$',                    # Remove deadstock notes
            r'\s*\(GS\)$',                    # Keep GS but consider removing if no match
        ]

        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Preserve important details like years, "without laces", etc.
        # Only clean up excessive spacing and normalize some terms
        replacements = {
            'RETRO HIGH': 'High',     # Normalize retro terms
            'RETRO LOW': 'Low',       # Normalize retro terms  
            '1 85': '1',              # Fix spacing issues
        }

        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)

        # Clean up spacing but preserve all meaningful words
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned[:80]  # Increased length to preserve more details

    def get_product_variants(self, product_id: str) -> List[Dict]:
        """Get all variants for a product"""
        try:
            headers = self.client._get_headers()
            response = requests.get(
                f'{self.client.base_url}/catalog/products/{product_id}/variants',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"   ❌ Error getting variants: {response.status_code}")
                return []

        except Exception as e:
            print(f"   ❌ Error getting variants: {str(e)}")
            return []

    def find_variant_by_size(self, variants: List[Dict], target_size: str, size_category: str) -> Tuple[Optional[Dict], bool]:
        """Find variant matching the target size"""
        target_size_clean = target_size.replace('.0', '').strip()

        # First try exact matches
        for variant in variants:
            # Check variantValue first (most direct)
            variant_value = str(variant.get('variantValue', '')).strip()
            if variant_value == target_size or variant_value == target_size_clean:
                return variant, False

            # Check default conversion
            size_chart = variant.get('sizeChart', {})
            default_conversion = size_chart.get('defaultConversion')
            if default_conversion:
                default_size = str(default_conversion.get('size', '')).strip()
                if default_size == target_size or default_size == target_size_clean:
                    return variant, False

        # Try extended matching with size suffixes (no longer marked as uncertain)
        numeric_size = re.sub(r'[^0-9.]', '', target_size_clean)
        if numeric_size:
            # Try different size suffixes that might match
            size_attempts = [
                f"{numeric_size}Y",    # Youth/GS
                f"{numeric_size}C",    # Child/PS  
                f"{numeric_size}W",    # Women's
                numeric_size,          # Plain numeric
            ]

            for attempt_size in size_attempts:
                for variant in variants:
                    variant_value = str(variant.get('variantValue', '')).strip()

                    if variant_value == attempt_size:
                        return variant, False

                    # Also check default conversion
                    size_chart = variant.get('sizeChart', {})
                    default_conversion = size_chart.get('defaultConversion')
                    if default_conversion:
                        default_size = str(default_conversion.get('size', '')).strip()
                        if default_size == attempt_size:
                            return variant, False

        return None, False

    def get_variant_market_data(self, product_id: str, variant_id: str) -> Optional[Dict]:
        """Get market data for specific variant"""
        try:
            headers = self.client._get_headers()
            response = requests.get(
                f'{self.client.base_url}/catalog/products/{product_id}/variants/{variant_id}/market-data',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"   ❌ Market data error: {response.status_code}")
                return None

        except Exception as e:
            print(f"   ❌ Market data error: {str(e)}")
            return None



    def get_alias_pricing_data(self, shoe_name: str, size: str) -> Optional[Dict]:
        """Get pricing data from Alias API for the requested data points"""
        try:
            import requests
            
            # Alias API configuration
            api_key = "goatapi_167AEOZwPmcFAwZ2RbHv7AaGfSYpdF2wq1zdxzT"
            base_url = "https://api.alias.org/api/v1"
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # Parse size to float
            try:
                size_float = float(size.replace('Y', '').replace('W', '').replace('C', ''))
            except (ValueError, AttributeError):
                size_float = 10.0  # Default size if parsing fails
            
            # Step 1: Search for the shoe in Alias catalog with multiple strategies
            alias_sku = None
            catalog_id = None
            alias_name = None
            
            # Strategy 1: Direct search with original name
            print(f"   🔍 Searching Alias for: {shoe_name}")
            search_data = self._try_alias_search(base_url, headers, shoe_name)
            
            if search_data and search_data.get('catalog_items'):
                catalog_item = search_data['catalog_items'][0]
                catalog_id = catalog_item.get('catalog_id')
                alias_name = catalog_item.get('name', 'Unknown')
                
                # Try multiple fields for SKU extraction
                alias_sku = (catalog_item.get('sku') or 
                           catalog_item.get('style_id') or 
                           catalog_item.get('style_code') or 
                           catalog_item.get('product_id') or 
                           catalog_item.get('model_number') or 
                           '')
                
                print(f"   ✅ Found Alias match: {alias_name}")
                if alias_sku:
                    print(f"   📋 Alias SKU: {alias_sku}")
            
            # Strategy 2: If no match and this looks like a SKU, try cleaning it
            if not catalog_id and self._looks_like_sku(shoe_name):
                cleaned_sku = self._clean_sku_for_alias_search(shoe_name)
                if cleaned_sku != shoe_name:
                    print(f"   🔍 Trying cleaned SKU: {cleaned_sku}")
                    search_data = self._try_alias_search(base_url, headers, cleaned_sku)
                    
                    if search_data and search_data.get('catalog_items'):
                        catalog_item = search_data['catalog_items'][0]
                        catalog_id = catalog_item.get('catalog_id')
                        alias_name = catalog_item.get('name', 'Unknown')
                        alias_sku = (catalog_item.get('sku') or 
                                   catalog_item.get('style_id') or 
                                   catalog_item.get('style_code') or 
                                   '')
                        print(f"   ✅ Found Alias match with cleaned SKU: {alias_name}")
            
            # Strategy 3: If still no match and we have a SKU with spaces, try with dashes
            if not catalog_id and ' ' in shoe_name:
                sku_with_dash = shoe_name.replace(' ', '-')
                print(f"   🔍 Trying SKU with dash: {sku_with_dash}")
                search_data = self._try_alias_search(base_url, headers, sku_with_dash)
                
                if search_data and search_data.get('catalog_items'):
                    catalog_item = search_data['catalog_items'][0]
                    catalog_id = catalog_item.get('catalog_id')
                    alias_name = catalog_item.get('name', 'Unknown')
                    alias_sku = (catalog_item.get('sku') or 
                               catalog_item.get('style_id') or 
                               catalog_item.get('style_code') or 
                               '')
                    print(f"   ✅ Found Alias match with dash: {alias_name}")
            
            if not catalog_id:
                print(f"   ❌ No Alias catalog match found")
                return None
            
            # Step 2: Get pricing data with all the requested parameters
            params = {
                'catalog_id': catalog_id,
                'size': size_float,
                'product_condition': 'PRODUCT_CONDITION_NEW',
                'packaging_condition': 'PACKAGING_CONDITION_GOOD_CONDITION'
            }
            
            # Get overall availability (ship to verify + lowest with you)
            overall_response = requests.get(
                f"{base_url}/pricing_insights/availability",
                headers=headers,
                params=params,
                timeout=15
            )
            
            # Get consigned availability (lowest consigned + consignment price)
            consigned_params = params.copy()
            consigned_params['consigned'] = True
            consigned_response = requests.get(
                f"{base_url}/pricing_insights/availability",
                headers=headers,
                params=consigned_params,
                timeout=15
            )
            
            # Get recent sales for last with you and last consigned
            sales_response = requests.get(
                f"{base_url}/pricing_insights/recent_sales",
                headers=headers,
                params={**params, 'limit': 10},
                timeout=15
            )
            
            # Get recent consigned sales
            consigned_sales_params = params.copy()
            consigned_sales_params.update({'consigned': True, 'limit': 10})
            consigned_sales_response = requests.get(
                f"{base_url}/pricing_insights/recent_sales",
                headers=headers,
                params=consigned_sales_params,
                timeout=15
            )
            
            # Process the responses
            overall_data = overall_response.json().get('availability', {}) if overall_response.status_code == 200 else {}
            consigned_data = consigned_response.json().get('availability', {}) if consigned_response.status_code == 200 else {}
            sales_data = sales_response.json().get('recent_sales', []) if sales_response.status_code == 200 else []
            consigned_sales_data = consigned_sales_response.json().get('recent_sales', []) if consigned_sales_response.status_code == 200 else []
            
            # Extract the specific data points you requested
            def cents_to_dollars(cents):
                if cents is None:
                    return None
                try:
                    return float(cents) / 100
                except (ValueError, TypeError):
                    return None
            
            # Get last sale data
            last_sale = sales_data[0] if sales_data else {}
            last_consigned = consigned_sales_data[0] if consigned_sales_data else {}
            
            # Extract prices with better handling of None/0 values
            ship_to_verify = cents_to_dollars(overall_data.get('lowest_listing_price_cents'))
            consignment = cents_to_dollars(consigned_data.get('lowest_listing_price_cents'))
            
            # If consignment price is None or 0, it means no consigned listings available
            if consignment is None or consignment == 0:
                consignment = None
            
            result = {
                # Ship to verify price
                'ship_to_verify_price': ship_to_verify,
                
                # Consignment price (None if no consigned listings)
                'consignment_price': consignment,
                
                # Lowest with you (overall lowest)
                'lowest_with_you': ship_to_verify,
                
                # Lowest consigned (None if no consigned listings)
                'lowest_consigned': consignment,
                
                # Last with you (most recent sale)
                'last_with_you_price': cents_to_dollars(last_sale.get('price_cents')),
                'last_with_you_date': last_sale.get('purchased_at'),
                
                # Last consigned
                'last_consigned_price': cents_to_dollars(last_consigned.get('price_cents')),
                'last_consigned_date': last_consigned.get('purchased_at'),
                
                # Include SKU for verification
                'alias_sku': alias_sku,
            }
            
            print(f"   💰 Alias data: Ship ${result['ship_to_verify_price'] or 'N/A'} | Consigned ${result['consignment_price'] or 'N/A'}")
            
            return result
            
        except Exception as e:
            print(f"   ❌ Alias API error: {str(e)}")
            return None
    
    def calculate_weekly_volume(self, shoe_name: str, size: str) -> float:
        """Calculate last-7-days sales count on Alias for the exact size (not velocity)."""
        try:
            print(f"   📊 Calculating weekly volume for: {shoe_name} (Size {size})")

            # Build search terms and find catalog match
            search_terms = self.volume_analyzer._extract_search_terms(shoe_name)
            catalog_match = self.volume_analyzer.search_catalog_improved(search_terms)
            if not catalog_match:
                print(f"   ⚠️ No Alias catalog match for volume")
                return 0.0

            # Parse size to float
            try:
                size_float = float(str(size).replace('Y', '').replace('W', '').replace('C', ''))
            except (ValueError, TypeError):
                print(f"   ⚠️ Invalid size for volume: {size}")
                return 0.0

            # Get recent sales for this size
            sales_data = self.volume_analyzer._get_sales_for_size(catalog_match['catalog_id'], size_float)
            if not sales_data:
                print(f"   ⚠️ No sales data for this size")
                return 0.0

            # Count last 7 days
            now = datetime.now(timezone.utc)
            one_week_ago = now.timestamp() - 7 * 24 * 3600
            count_last_week = 0
            for sale in sales_data:
                date_str = sale.get('purchased_at')
                if not date_str:
                    continue
                try:
                    if 'T' in date_str:
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        dt = datetime.fromisoformat(date_str)
                    # Convert to UTC timestamp
                    ts = dt.timestamp()
                    if ts >= one_week_ago:
                        count_last_week += 1
                except Exception:
                    continue

            print(f"   📈 Weekly volume (last 7 days): {count_last_week}")
            return float(count_last_week)

        except Exception as e:
            print(f"   ❌ Volume calculation error: {str(e)}")
            return 0.0
    
    def calculate_price_offer(self, item: InventoryItem, overrides: Optional[Dict] = None) -> Tuple[Optional[float], str]:
        """Calculate price offer ensuring 20% margin vs GOAT absolute lowest, with volume-specific rules.
        Optionally accepts overrides for numeric values to avoid timing/order issues.
        overrides keys: stockx_bid, goat_ship_to_verify, goat_consigned, weekly_volume
        """
        try:
            # Extract numeric values
            if overrides:
                stockx_bid = overrides.get('stockx_bid') if overrides.get('stockx_bid') is not None else (self._parse_price(item.stockx_bid) if item.stockx_bid else None)
                stockx_ask = overrides.get('stockx_ask') if overrides.get('stockx_ask') is not None else (self._parse_price(item.stockx_ask) if item.stockx_ask else None)
                goat_consigned = overrides.get('goat_consigned') if overrides.get('goat_consigned') is not None else (self._parse_price(item.lowest_consigned) if item.lowest_consigned else None)
                goat_ship_to_verify = overrides.get('goat_ship_to_verify') if overrides.get('goat_ship_to_verify') is not None else (self._parse_price(item.ship_to_verify_price) if item.ship_to_verify_price else None)
                weekly_volume = overrides.get('weekly_volume') if overrides.get('weekly_volume') is not None else (item.weekly_volume or 0.0)
            else:
                stockx_bid = self._parse_price(item.stockx_bid) if item.stockx_bid else None
                stockx_ask = self._parse_price(item.stockx_ask) if item.stockx_ask else None
                goat_consigned = self._parse_price(item.lowest_consigned) if item.lowest_consigned else None
                goat_ship_to_verify = self._parse_price(item.ship_to_verify_price) if item.ship_to_verify_price else None
                weekly_volume = item.weekly_volume or 0.0
            
            # Determine GOAT absolute lowest (including both consigned and ship-to-verify)
            valid_goat_prices = [p for p in [goat_consigned, goat_ship_to_verify] if p is not None and p > 0]
            goat_absolute_lowest = min(valid_goat_prices) if valid_goat_prices else None
            target_max_payment = goat_absolute_lowest * 0.8 if goat_absolute_lowest else None
            
            # Get weekly volume
            is_high_volume = weekly_volume >= 3.0
            
            print(f"   💰 Price Offer Calculation:")
            print(f"   📊 Weekly Volume: {weekly_volume:.2f} ({'High' if is_high_volume else 'Low'} volume)")
            print(f"   💵 StockX Bid: ${stockx_bid or 'N/A'}")
            print(f"   💵 StockX Ask: ${stockx_ask or 'N/A'}")
            print(f"   🐐 GOAT Absolute Lowest: ${goat_absolute_lowest or 'N/A'}")
            print(f"   🎯 Max Pay for 20% margin (80% of GOAT): ${target_max_payment or 'N/A'}")
            
            # Apply corrected pricing rules
            if is_high_volume:
                # High volume (≥3/week): ensure 20% margin vs GOAT; prefer paying bid if within threshold
                if goat_absolute_lowest and target_max_payment:
                    if stockx_bid is not None:
                        if stockx_bid <= target_max_payment:
                            offer_price = stockx_bid
                            reasoning = f"High volume ({weekly_volume:.1f}/week): Bid ${stockx_bid:.2f} ≤ 80% of GOAT ${goat_absolute_lowest:.2f} → offer bid"
                            print(f"   ✅ {reasoning}")
                            return offer_price, reasoning
                        else:
                            offer_price = target_max_payment
                            reasoning = f"High volume ({weekly_volume:.1f}/week): Bid ${stockx_bid:.2f} exceeds 80% of GOAT ${goat_absolute_lowest:.2f} → offer ${offer_price:.2f} (GOAT -20%)"
                            print(f"   ✅ {reasoning}")
                            return offer_price, reasoning
                    else:
                        # No bid; still enforce 20% margin using GOAT
                        offer_price = target_max_payment
                        reasoning = f"High volume ({weekly_volume:.1f}/week): No bid, offer ${offer_price:.2f} (GOAT ${goat_absolute_lowest:.2f} -20%)"
                        print(f"   ✅ {reasoning}")
                        return offer_price, reasoning
                else:
                    # No GOAT data; fallback to bid if available
                    if stockx_bid is not None:
                        offer_price = stockx_bid
                        reasoning = f"High volume ({weekly_volume:.1f}/week): No GOAT data, offer StockX bid ${offer_price:.2f}"
                        print(f"   ✅ {reasoning}")
                        return offer_price, reasoning
                    reasoning = f"High volume ({weekly_volume:.1f}/week): No GOAT or bid data"
                    print(f"   ❌ {reasoning}")
                    return None, reasoning
            else:
                # Low volume (≤2/week): always make an offer; ensure 20% margin when GOAT available
                if goat_absolute_lowest and target_max_payment:
                    if stockx_bid is not None:
                        if stockx_bid <= target_max_payment:
                            offer_price = stockx_bid
                            reasoning = f"Low volume ({weekly_volume:.1f}/week): Bid ${stockx_bid:.2f} ≤ 80% of GOAT ${goat_absolute_lowest:.2f} → offer bid"
                            print(f"   ✅ {reasoning}")
                            return offer_price, reasoning
                        else:
                            offer_price = target_max_payment
                            reasoning = f"Low volume ({weekly_volume:.1f}/week): Bid ${stockx_bid:.2f} exceeds 80% of GOAT ${goat_absolute_lowest:.2f} → offer ${offer_price:.2f} (GOAT -20%)"
                            print(f"   ✅ {reasoning}")
                            return offer_price, reasoning
                    else:
                        offer_price = target_max_payment
                        reasoning = f"Low volume ({weekly_volume:.1f}/week): No bid, offer ${offer_price:.2f} (GOAT ${goat_absolute_lowest:.2f} -20%)"
                        print(f"   ✅ {reasoning}")
                        return offer_price, reasoning
                else:
                    # No GOAT data; if bid exists, offer bid; otherwise cannot compute
                    if stockx_bid is not None:
                        offer_price = stockx_bid
                        reasoning = f"Low volume ({weekly_volume:.1f}/week): No GOAT data, offer StockX bid ${offer_price:.2f}"
                        print(f"   ✅ {reasoning}")
                        return offer_price, reasoning
                    reasoning = f"Low volume ({weekly_volume:.1f}/week): No GOAT or bid data"
                    print(f"   ❌ {reasoning}")
                    return None, reasoning
                    
        except Exception as e:
            reasoning = f"Error calculating price offer: {str(e)}"
            print(f"   ❌ {reasoning}")
            return None, reasoning
    
    def _parse_price(self, price_str: str) -> Optional[float]:
        """Parse price string to float, handling $ and other formatting"""
        if not price_str:
            return None
        try:
            # Remove $ and other non-numeric characters except decimal point
            cleaned = re.sub(r'[^\d.]', '', str(price_str))
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None
    
    def _try_alias_search(self, base_url: str, headers: Dict, query: str) -> Optional[Dict]:
        """Try to search Alias API with a given query"""
        try:
            search_response = requests.get(
                f"{base_url}/catalog",
                headers=headers,
                params={'query': query, 'limit': 1},
                timeout=15
            )
            
            if search_response.status_code == 200:
                return search_response.json()
            else:
                print(f"   ⚠️ Alias search failed for '{query}': {search_response.status_code}")
                return None
                
        except Exception as e:
            print(f"   ⚠️ Alias search error for '{query}': {e}")
            return None
    
    def _looks_like_sku(self, text: str) -> bool:
        """Check if text looks like a SKU"""
        # SKUs are typically short alphanumeric codes
        if not (4 <= len(text) <= 25):
            return False
            
        # Must be mostly alphanumeric with limited special chars
        if not re.match(r'^[A-Za-z0-9\s\-]+$', text):
            return False
            
        # Should have at least some letters and numbers
        has_letters = bool(re.search(r'[A-Za-z]', text))
        has_numbers = bool(re.search(r'\d', text))
        if not (has_letters and has_numbers):
            return False
            
        # If it contains many obvious shoe terms, it's probably not a SKU
        # But allow single short terms that might be in SKUs
        shoe_terms = ['jordan', 'nike', 'air force', 'dunk low', 'yeezy', 'adidas', 'retro', 'high og', 'low og']
        text_lower = text.lower()
        if any(term in text_lower for term in shoe_terms):
            return False
            
        # If it has descriptive words, it's probably not a SKU
        descriptive_words = ['travis', 'canary', 'royal', 'cement', 'fire', 'red', 'navy', 'champion', 'mauve']
        word_count = sum(1 for word in descriptive_words if word in text_lower)
        if word_count >= 2:  # Multiple descriptive words = not a SKU
            return False
            
        # If it has size indicators at the end, it's not a pure SKU
        if re.search(r'\s+\d+(?:\.\d+)?[mwcy]\s*$', text_lower):
            return False
            
        # If it has obvious condition terms, it's not a SKU
        condition_terms = ['ds', 'vnds', 'og all', 'nb', 'used']
        if any(term in text_lower for term in condition_terms):
            return False
            
        # If it's mostly just letters and numbers in a pattern, it's likely a SKU
        # Common SKU patterns: AB1234, AB1234-567, AB1234 567
        sku_patterns = [
            r'^[A-Z]{1,3}\d{4,6}$',           # AB1234
            r'^[A-Z]{1,3}\d{4,6}[\s\-]\d{2,4}$',  # AB1234-567 or AB1234 567
            r'^[A-Z0-9]{4,12}$',              # Mixed alphanumeric
        ]
        
        text_clean = text.replace(' ', '').replace('-', '')
        for pattern in sku_patterns:
            if re.match(pattern, text_clean, re.IGNORECASE):
                return True
        
        return False
    
    def _clean_sku_for_alias_search(self, sku: str) -> str:
        """Clean SKU for better Alias search results"""
        # Remove extra spaces and normalize
        cleaned = re.sub(r'\s+', ' ', sku.strip())
        
        # Try removing spaces entirely
        if ' ' in cleaned:
            return cleaned.replace(' ', '')
        
        return cleaned

    def _generate_sku_variations(self, sku: str) -> List[str]:
        """Generate SKU variations for better matching (shared with advanced)"""
        variations = [sku]
        if '-' in sku:
            variations.append(sku.replace('-', ' '))
        if ' ' in sku:
            variations.append(sku.replace(' ', '-'))
            variations.append(sku.replace(' ', ''))
        return list(set(variations))

    def _normalize_sku_for_search(self, sku: str) -> str:
        """Normalize SKU for optimal search (shared with advanced)"""
        import re
        if not sku:
            return sku
        normalized = sku.upper().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        if re.match(r'^[A-Z]{2}\d{3,4}\s+\d{3}$', normalized):
            normalized = normalized.replace(' ', '-')
        if re.match(r'^\d{6}\s+\d{3}$', normalized):
            normalized = normalized.replace(' ', '-')
        normalized = re.sub(r'[_\s]+', '-', normalized)
        normalized = normalized.rstrip('-')
        return normalized

    def search_stockx_for_item(self, item: InventoryItem) -> bool:
        """Search StockX for inventory item"""
        # Check if this is a SKU-based search
        is_sku_search = getattr(item, 'is_sku_search', False)
        
        if is_sku_search:
            return self._search_by_sku(item)
        else:
            return self._search_by_name(item)
    
    def _search_by_sku(self, item: InventoryItem) -> bool:
        """Search StockX using SKU/style ID with normalization and variations"""
        sku = item.shoe_name
        size_normalized, size_category = self.normalize_size(item.size)
        cache_key = f"sku_{sku}_{size_normalized}_{size_category}"
        if cache_key in self.cache:
            return self._apply_cached_result(item, cache_key)
        try:
            print(f"🔍 SKU Search: '{sku}' (Size: {size_normalized} {size_category})", flush=True)
            # Normalize first
            normalized = self._normalize_sku_for_search(sku)
            candidates = [normalized] + self._generate_sku_variations(normalized)
            tried = set()
            for candidate in candidates:
                if candidate in tried:
                    continue
                tried.add(candidate)
                try:
                    search_results = self.client.search_products(candidate, page_size=10)
                except Exception as e:
                    print(f"   ⚠️ Search error for '{candidate}': {e}")
                    continue
                if search_results and search_results.get('products'):
                    best_product = self._find_best_sku_match(search_results['products'], candidate, size_category)
                    if best_product:
                        print(f"   ✅ SKU match via '{candidate}': {best_product['title'][:50]}...", flush=True)
                        return self._process_product_match(item, best_product, size_normalized, size_category, cache_key)
            print("   ❌ No suitable SKU match after normalization/variations")
            self.cache[cache_key] = None
            return False
        except Exception as e:
            print(f"   ❌ SKU search error: {str(e)}")
            if "429" in str(e):
                return "RATE_LIMITED"
            self.cache[cache_key] = None
            return False
    
    def _search_by_name(self, item: InventoryItem) -> bool:
        """Search StockX using shoe name"""
        search_query = self.clean_shoe_name_for_search(item.shoe_name)
        size_normalized, size_category = self.normalize_size(item.size)

        cache_key = f"{search_query}_{size_normalized}_{size_category}"

        if cache_key in self.cache:
            return self._apply_cached_result(item, cache_key)

        try:
            print(f"🔍 Name Search: '{search_query}' (Size: {size_normalized} {size_category})", flush=True)

            # Ensure authentication before search (in case it failed during init)
            try:
                search_results = self.client.search_products(search_query, page_size=10)
            except Exception as auth_error:
                if "tokens_full_scope.json" in str(auth_error) or "No such file" in str(auth_error):
                    print(f"   🔄 Authentication issue detected, retrying setup...")
                    self._setup_authentication()
                    # Retry the search after auth setup
                    search_results = self.client.search_products(search_query, page_size=10)
                else:
                    raise auth_error

            if not search_results['products']:
                print("   ❌ No products found", flush=True)
                self.cache[cache_key] = None
                return False

            best_product = self._find_best_product_match(
                search_results['products'], 
                search_query, 
                size_category
            )

            if not best_product:
                print("   ❌ No suitable product match")
                self.cache[cache_key] = None
                return False

            print(f"   ✅ Found: {best_product['title'][:50]}...", flush=True)
            return self._process_product_match(item, best_product, size_normalized, size_category, cache_key)

        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            # Check if this is a rate limiting error
            if "429" in str(e):
                return "RATE_LIMITED"
            self.cache[cache_key] = None
            return False
    
    def _try_sku_search(self, sku: str):
        """Try to search for a product by its SKU/style ID"""
        try:
            # Try different SKU search approaches
            # 1. Search with quotes for exact match
            search_results = self.client.search_products(f'"{sku}"', page_size=5)
            if search_results and search_results.get('products'):
                # Check if any results have exact SKU match
                for product in search_results['products']:
                    if product.get('style_id') == sku:
                        return search_results
            
            # 2. Try without quotes
            search_results = self.client.search_products(sku, page_size=10)
            return search_results
            
        except Exception as e:
            print(f"   ⚠️ SKU search attempt failed: {e}")
            return None
    
    def _find_best_sku_match(self, products: List[Dict], sku: str, size_category: str) -> Optional[Dict]:
        """Find best matching product for SKU search"""
        sku_upper = sku.upper()
        
        # First priority: Exact SKU match
        for product in products:
            product_sku = product.get('style_id', '').upper()
            if product_sku == sku_upper:
                print(f"   🎯 Exact SKU match: {product_sku}")
                return product
        
        # Second priority: SKU appears in style_id
        for product in products:
            product_sku = product.get('style_id', '').upper()
            if sku_upper in product_sku or product_sku in sku_upper:
                print(f"   🔍 Partial SKU match: {product_sku}")
                return product
        
        # Third priority: First result (if any)
        if products:
            print(f"   ⚠️ Using first search result for SKU: {sku}")
            return products[0]
        
        return None
    
    def _apply_cached_result(self, item: InventoryItem, cache_key: str) -> bool:
        """Apply cached search result to item"""
        cached_result = self.cache[cache_key]
        if cached_result:
            item.stockx_bid = f"${cached_result['bid']}" if cached_result['bid'] else None
            item.stockx_ask = f"${cached_result['ask']}" if cached_result['ask'] else None
            # Add cached Alias data
            if cached_result.get('lowest_consigned'):
                item.lowest_consigned = f"${cached_result['lowest_consigned']:.2f}"
            else:
                item.lowest_consigned = None
            if cached_result.get('last_consigned_price'):
                item.last_consigned_price = f"${cached_result['last_consigned_price']:.2f}"
            else:
                item.last_consigned_price = None
            item.last_consigned_date = self._convert_date_to_days_ago(cached_result.get('last_consigned_date'))
            if cached_result.get('lowest_with_you'):
                item.lowest_with_you = f"${cached_result['lowest_with_you']:.2f}"
            else:
                item.lowest_with_you = None
            if cached_result.get('last_with_you_price'):
                item.last_with_you_price = f"${cached_result['last_with_you_price']:.2f}"
            else:
                item.last_with_you_price = None
            item.last_with_you_date = self._convert_date_to_days_ago(cached_result.get('last_with_you_date'))
            if cached_result.get('consignment_price'):
                item.consignment_price = f"${cached_result['consignment_price']:.2f}"
            else:
                item.consignment_price = None
            if cached_result.get('ship_to_verify_price'):
                item.ship_to_verify_price = f"${cached_result['ship_to_verify_price']:.2f}"
            else:
                item.ship_to_verify_price = None
            item.stockx_sku = cached_result.get('sku')
            item.stockx_url = cached_result.get('url')
            item.stockx_size = cached_result.get('size')
            item.stockx_shoe_name = cached_result.get('shoe_name')
            item.bid_profit = f"${cached_result['bid_profit']:.2f}" if cached_result.get('bid_profit') is not None else None
            item.ask_profit = f"${cached_result['ask_profit']:.2f}" if cached_result.get('ask_profit') is not None else None
            item.weekly_volume = cached_result.get('weekly_volume')
            item.price_offer = f"${cached_result['price_offer']:.2f}" if cached_result.get('price_offer') is not None else None
            item.offer_reasoning = cached_result.get('offer_reasoning')
            return True
        return False
    
    def _process_product_match(self, item: InventoryItem, best_product: Dict, size_normalized: str, size_category: str, cache_key: str) -> bool:
        """Process a product match and get pricing data"""
        try:
            # Get variants for the product
            variants = self.get_product_variants(best_product['id'])

            if not variants:
                print("   ❌ No variants found")
                self.cache[cache_key] = None
                return False

            # Find matching variant by size
            matching_variant, _ = self.find_variant_by_size(variants, size_normalized, size_category)

            if not matching_variant:
                print(f"   ❌ Size {size_normalized} not found", flush=True)
                # Debug: show available sizes
                available_sizes = [str(v.get('variantValue', '')) for v in variants[:10]]
                print(f"   📏 Available sizes: {', '.join(available_sizes)}", flush=True)
                self.cache[cache_key] = None
                return False

            variant_id = matching_variant['variantId']
            variant_size = matching_variant.get('variantValue', size_normalized)

            print(f"   🎯 Found variant: {variant_size} (ID: {variant_id[:8]}...)")

            # Get market data for the specific variant
            print(f"   📊 Getting StockX market data...", flush=True)
            market_data = self.get_variant_market_data(best_product['id'], variant_id)

            if not market_data:
                print("   ❌ No StockX market data available")
                self.cache[cache_key] = None
                return False
             
            # Get Alias pricing data for the requested data points
            # Try with original shoe name first, then StockX name if no match
            alias_data = self.get_alias_pricing_data(item.shoe_name, str(variant_size))
            if not alias_data:
                alias_data = self.get_alias_pricing_data(best_product['title'], str(variant_size))
            
            # Calculate weekly volume (last 7 days count) and previous method (velocity*7)
            print(f"   📊 Calculating weekly volume...", flush=True)
            weekly_volume = self.calculate_weekly_volume(item.shoe_name, str(variant_size))
            item.weekly_volume = weekly_volume
            # Previous method for transparency
            try:
                prev_vol = self.volume_analyzer.get_weekly_volume(item.shoe_name, str(variant_size))
                item.weekly_volume_prev = prev_vol.get('weekly_volume') if isinstance(prev_vol, dict) else None
            except Exception:
                item.weekly_volume_prev = None
            
            # Extract pricing data
            bid_amount = market_data.get('highestBidAmount')
            ask_amount = market_data.get('lowestAskAmount')

            # Calculate profit margins
            original_price = self._parse_price(item.price)
            bid_profit = None
            ask_profit = None

            if original_price and bid_amount:
                bid_profit = float(bid_amount) - original_price

            if original_price and ask_amount:
                ask_profit = float(ask_amount) - original_price

            # Construct StockX URL using urlKey
            stockx_url = None
            url_key = best_product.get('url_key')
            if url_key:
                stockx_url = f"https://stockx.com/{url_key}"

            # Populate item with StockX market data
            item.stockx_bid = f"${bid_amount}" if bid_amount else None
            item.stockx_ask = f"${ask_amount}" if ask_amount else None
            # Add Alias data to item
            if alias_data:
                item.lowest_consigned = f"${alias_data['lowest_consigned']:.2f}" if alias_data.get('lowest_consigned') else None
                item.last_consigned_price = f"${alias_data['last_consigned_price']:.2f}" if alias_data.get('last_consigned_price') else None
                item.last_consigned_date = self._convert_date_to_days_ago(alias_data.get('last_consigned_date'))
                item.lowest_with_you = f"${alias_data['lowest_with_you']:.2f}" if alias_data.get('lowest_with_you') else None
                item.last_with_you_price = f"${alias_data['last_with_you_price']:.2f}" if alias_data.get('last_with_you_price') else None
                item.last_with_you_date = self._convert_date_to_days_ago(alias_data.get('last_with_you_date'))
                item.consignment_price = f"${alias_data['consignment_price']:.2f}" if alias_data.get('consignment_price') else None
                item.ship_to_verify_price = f"${alias_data['ship_to_verify_price']:.2f}" if alias_data.get('ship_to_verify_price') else None
            else:
                item.lowest_consigned = None
                item.last_consigned_price = None
                item.last_consigned_date = None
                item.lowest_with_you = None
                item.last_with_you_price = None
                item.last_with_you_date = None
                item.consignment_price = None
                item.ship_to_verify_price = None
            item.stockx_sku = best_product.get('style_id', '')
            item.stockx_url = stockx_url
            item.stockx_size = str(variant_size)
            item.stockx_shoe_name = best_product['title']
            item.bid_profit = f"${bid_profit:.2f}" if bid_profit is not None else None
            item.ask_profit = f"${ask_profit:.2f}" if ask_profit is not None else None

            # Now that item has StockX and GOAT data, calculate price offer using raw numbers to avoid string parsing mishaps
            print(f"   💰 Calculating price offer...", flush=True)
            offer_price, offer_reasoning = self.calculate_price_offer(
                item,
                overrides={
                    'stockx_bid': float(bid_amount) if bid_amount is not None else None,
                    'stockx_ask': float(ask_amount) if ask_amount is not None else None,
                    'goat_ship_to_verify': float(alias_data['ship_to_verify_price']) if alias_data and alias_data.get('ship_to_verify_price') is not None else None,
                    'goat_consigned': float(alias_data['consignment_price']) if alias_data and alias_data.get('consignment_price') is not None else None,
                    'weekly_volume': float(weekly_volume) if weekly_volume is not None else 0.0
                }
            )
            item.price_offer = f"${offer_price:.2f}" if offer_price is not None else None
            item.offer_reasoning = offer_reasoning

            # Build result for caching and logs (includes offer and volume)
            result = {
                'bid': bid_amount,
                'ask': ask_amount,
                'lowest_consigned': alias_data.get('lowest_consigned') if alias_data else None,
                'last_consigned_price': alias_data.get('last_consigned_price') if alias_data else None,
                'last_consigned_date': alias_data.get('last_consigned_date') if alias_data else None,
                'lowest_with_you': alias_data.get('lowest_with_you') if alias_data else None,
                'last_with_you_price': alias_data.get('last_with_you_price') if alias_data else None,
                'last_with_you_date': alias_data.get('last_with_you_date') if alias_data else None,
                'consignment_price': alias_data.get('consignment_price') if alias_data else None,
                'ship_to_verify_price': alias_data.get('ship_to_verify_price') if alias_data else None,
                'weekly_volume': weekly_volume,
                'weekly_volume_prev': item.weekly_volume_prev,
                'price_offer': offer_price,
                'offer_reasoning': offer_reasoning,
                'sku': item.stockx_sku,
                'url': item.stockx_url,
                'size': item.stockx_size,
                'shoe_name': item.stockx_shoe_name,
                'bid_profit': bid_profit,
                'ask_profit': ask_profit
            }

            self.cache[cache_key] = result

            print(f"   ✅ StockX Data Retrieved:", flush=True)
            print(f"   💰 Bid: ${result['bid'] or 'N/A'} | Ask: ${result['ask'] or 'N/A'} | Size: {result['size']}", flush=True)
            print(f"   📋 SKU: {result['sku']} | Shoe: {result['shoe_name'][:40]}...", flush=True)
            if alias_data:
                print(f"   ✅ Alias Data Retrieved:", flush=True)
                print(f"   📦 Ship: ${alias_data['ship_to_verify_price'] or 'N/A'} | Consigned: ${alias_data['consignment_price'] or 'N/A'}", flush=True)
                
                # SKU verification
                stockx_sku = result['sku']
                alias_sku = alias_data.get('alias_sku', '')
                if stockx_sku and alias_sku:
                    # Normalize both SKUs for comparison (remove dashes, spaces, make uppercase)
                    stockx_normalized = re.sub(r'[-\s]', '', stockx_sku.upper())
                    alias_normalized = re.sub(r'[-\s]', '', alias_sku.upper())
                    
                    if stockx_normalized == alias_normalized:
                        print(f"   ✅ SKU Match Verified: {stockx_sku}", flush=True)
                    else:
                        print(f"   ⚠️  SKU Mismatch: StockX({stockx_sku}) vs Alias({alias_sku})", flush=True)
                elif not alias_sku:
                    print(f"   ⚠️  No Alias SKU available for verification", flush=True)
            return True

        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            # Check if this is a rate limiting error
            if "429" in str(e):
                return "RATE_LIMITED"
            self.cache[cache_key] = None
            return False

    def _find_best_product_match(self, products: List[Dict], search_query: str, size_category: str) -> Optional[Dict]:
        """Find best matching product"""
        search_lower = search_query.lower()

        scored_products = []

        for product in products:
            title_lower = product['title'].lower()

            score = 0
            search_words = search_lower.split()
            title_words = title_lower.split()

            for word in search_words:
                if word in title_words:
                    score += 2
                elif any(word in title_word for title_word in title_words):
                    score += 1

            if 'jordan 1' in search_lower and 'jordan 1' in title_lower:
                score += 5
            elif 'jordan 4' in search_lower and 'jordan 4' in title_lower:
                score += 5
            elif 'dunk' in search_lower and 'dunk' in title_lower:
                score += 3
            elif 'yeezy' in search_lower and 'yeezy' in title_lower:
                score += 3

            if size_category == "gs" and ('gs' in title_lower or 'grade school' in title_lower):
                score += 3
            elif size_category == "ps" and ('ps' in title_lower or 'preschool' in title_lower):
                score += 3
            elif size_category == "women" and ("women" in title_lower or " w " in title_lower):
                score += 2

            scored_products.append((score, product))

        scored_products.sort(key=lambda x: x[0], reverse=True)

        if scored_products and scored_products[0][0] > 0:
            return scored_products[0][1]

        return None

    def process_inventory(self, csv_file: str, output_file: str = None) -> str:
        """Process CSV inventory"""
        if not output_file:
            input_path = Path(csv_file)
            # Always use .csv extension for output files
            output_filename = f"stockx_enhanced_{input_path.stem}.csv"
            # Save generated outputs into top-level uploads directory to avoid repo root clutter
            uploads_dir = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads'))
            try:
                uploads_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            output_file = uploads_dir / output_filename

        print(f"📊 Processing CSV inventory: {csv_file}", flush=True)
        print(f"💾 Output will be saved to: {output_file}", flush=True)
        print("=" * 80, flush=True)

        items = self.parse_csv_flexible(csv_file)

        if not items:
            print("❌ No inventory items found")
            return ""

        print(f"✅ Parsed {len(items)} inventory items", flush=True)
        
        # Use shared processing logic
        return self._process_items_and_save(items, output_file)

    def process_pasted_list(self, text_file: str, output_file: str = None) -> str:
        """Process pasted list format (separate from CSV processing)"""
        if not output_file:
            input_path = Path(text_file)
            # Always use .csv extension for output files
            output_filename = f"stockx_enhanced_{input_path.stem}.csv"
            uploads_dir = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads'))
            try:
                uploads_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            output_file = uploads_dir / output_filename

        print(f"📋 Processing pasted list: {text_file}", flush=True)
        print(f"💾 Output will be saved to: {output_file}", flush=True)
        print("=" * 80, flush=True)

        # Read as text and parse
        with open(text_file, 'r', encoding='utf-8') as file:
            content = file.read().strip()
        
        items = self.parse_pasted_list(content)

        if not items:
            print("❌ No inventory items found in pasted list")
            return ""

        print(f"✅ Parsed {len(items)} inventory items from pasted list", flush=True)
        
        # Continue with normal processing
        return self._process_items_and_save(items, output_file)
    
    def _process_items_and_save(self, items: List[InventoryItem], output_file: str) -> str:
        """Common processing logic for both CSV and pasted list"""
        print(f"\n🔍 Processing {len(items)} items...", flush=True)
        
        # Calculate estimated time (2 seconds per item)
        estimated_seconds = len(items) * 2
        estimated_minutes = estimated_seconds / 60
        print(f"⏱️  Estimated time: {estimated_minutes:.1f} minutes", flush=True)
        print(f"🔄 Processing at safe rate (30 items/minute) to avoid API limits", flush=True)
        print("=" * 80, flush=True)

        start_time = time.time()
        
        for i, item in enumerate(items, 1):
            print(f"\n[{i}/{len(items)}] {item.shoe_name} - Size {item.size}", flush=True)

            # Retry logic for rate limiting
            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count <= max_retries and not success:
                result = self.search_stockx_for_item(item)
                
                if result == "RATE_LIMITED":
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"   ⏳ Rate limited! Waiting 2 seconds and retrying (attempt {retry_count}/{max_retries})...", flush=True)
                        time.sleep(2.0)  # Wait the normal interval
                    else:
                        print(f"   ❌ Max retries reached for rate limiting - skipping item", flush=True)
                        break
                elif result:
                    success = True
                    self.matches_found += 1
                    break
                else:
                    # Regular failure (not rate limited)
                    break

            self.processed_count += 1

            # Optimal rate limiting based on testing: 2 seconds = 30 requests/min
            # (only sleep if we didn't already sleep due to rate limiting)
            if not (result == "RATE_LIMITED" and retry_count > 0):
                time.sleep(2.0)

            # Progress update every 5 items with time estimation
            if i % 5 == 0:
                elapsed = time.time() - start_time
                remaining_items = len(items) - i
                remaining_time = (remaining_items * 2) / 60  # 2 seconds per item
                
                progress_percent = (i / len(items)) * 100
                print(f"   📊 Progress: {i}/{len(items)} ({progress_percent:.1f}%) - {self.matches_found} matches found", flush=True)
                print(f"   ⏱️  Estimated time remaining: {remaining_time:.1f} minutes", flush=True)

        self._write_enhanced_csv(items, output_file)

        print(f"\n" + "=" * 80, flush=True)
        print(f"📊 PROCESSING COMPLETE!", flush=True)
        print(f"✅ Processed: {self.processed_count} items", flush=True)
        print(f"🎯 Found StockX matches: {self.matches_found} items", flush=True)
        print(f"💾 Enhanced CSV saved: {output_file}", flush=True)

        return output_file

    def _write_enhanced_csv(self, items: List[InventoryItem], output_file: str):
        """Write enhanced CSV preserving original columns with smart ordering"""
        if not items:
            return
            
        # Get all original column names from first item
        original_columns = list(items[0].original_data.keys()) if items[0].original_data else []
        
        # Define our new columns that we want to add
        our_columns = [
            'quantity', 'condition', 'stockx_bid', 'stockx_ask',
            'lowest_consigned', 'last_consigned_price', 'last_consigned_date', 
            'lowest_with_you', 'last_with_you_price', 'last_with_you_date',
            'consignment_price', 'ship_to_verify_price',
            'weekly_volume', 'weekly_volume_prev', 'price_offer', 'offer_reasoning',
            # Bulk advanced-style simple metrics for spreadsheet use
            'final_recommendation',
            'price_offer_numeric',
            'stockx_bid_numeric', 'stockx_ask_numeric',
            'goat_ship_to_verify_numeric', 'goat_consignment_numeric', 'goat_absolute_lowest',
            'last_with_you_price_numeric', 'last_with_you_days_ago',
            'last_consigned_price_numeric', 'last_consigned_days_ago',
            'profit_vs_goat_lowest_gross', 'return_vs_goat_lowest_gross_pct',
            'profit_vs_goat_consigned_gross', 'return_vs_goat_consigned_gross_pct',
            'profit_vs_stockx_ask_gross', 'return_vs_stockx_ask_gross_pct',
            'stockx_sku', 'stockx_url', 'stockx_size', 'stockx_shoe_name'
        ]
        
        # Smart column ordering based on user requirements:
        # 1. Original columns to the left, but reordered intelligently
        # 2. Condition before shoe name
        # 3. Price right after size
        # 4. Our new columns in specified order
        
        ordered_columns = []
        remaining_original = original_columns.copy()
        
        # Add condition columns first (to left of shoe name)
        condition_cols = [col for col in original_columns if 'condition' in col.lower()]
        for col in condition_cols:
            if col in remaining_original:
                ordered_columns.append(col)
                remaining_original.remove(col)
        
        # Add shoe name column
        shoe_cols = [col for col in original_columns if any(word in col.lower() for word in ['shoe', 'name', 'product', 'item'])]
        for col in shoe_cols:
            if col in remaining_original:
                ordered_columns.append(col)
                remaining_original.remove(col)
        
        # Add size column
        size_cols = [col for col in original_columns if 'size' in col.lower()]
        for col in size_cols:
            if col in remaining_original:
                ordered_columns.append(col)
                remaining_original.remove(col)
        
        # Add price column right after size
        price_cols = [col for col in original_columns if any(word in col.lower() for word in ['price', 'cost', 'amount'])]
        for col in price_cols:
            if col in remaining_original:
                ordered_columns.append(col)
                remaining_original.remove(col)
        
        # Add any remaining original columns
        ordered_columns.extend(remaining_original)
        
        # Add our new columns
        ordered_columns.extend(our_columns)
        
        # Write the CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=ordered_columns)
            writer.writeheader()

            for item in items:
                row = {}
                
                # Add original data
                for col in original_columns:
                    if col in item.original_data:
                        value = item.original_data[col]
                        # Update condition with extracted notes if it's a condition column
                        if 'condition' in col.lower():
                            value = item.condition  # Use updated condition with notes
                        row[col] = value
                
                # Compute numeric helpers for advanced-style simple metrics
                offer_num = self._parse_price(item.price_offer)
                stockx_bid_num = self._parse_price(item.stockx_bid)
                stockx_ask_num = self._parse_price(item.stockx_ask)
                goat_ship_num = self._parse_price(item.ship_to_verify_price)
                goat_consigned_num = self._parse_price(item.consignment_price)
                goat_prices = [p for p in [goat_ship_num, goat_consigned_num] if p is not None and p > 0]
                goat_abs_lowest = min(goat_prices) if goat_prices else None
                last_with_you_price_num = self._parse_price(item.last_with_you_price)
                last_with_you_days = item.last_with_you_date or ''
                last_consigned_price_num = self._parse_price(item.last_consigned_price)
                last_consigned_days = item.last_consigned_date or ''

                def fmt(x):
                    return f"${x:.2f}" if isinstance(x, (int, float)) and x is not None else ''

                # Gross profit/returns (no fees assumed)
                if offer_num and goat_abs_lowest:
                    profit_goat_lowest = goat_abs_lowest - offer_num
                    return_goat_lowest_pct = (profit_goat_lowest / offer_num * 100) if offer_num > 0 else None
                else:
                    profit_goat_lowest = None
                    return_goat_lowest_pct = None

                if offer_num and goat_consigned_num:
                    profit_goat_consigned = goat_consigned_num - offer_num
                    return_goat_consigned_pct = (profit_goat_consigned / offer_num * 100) if offer_num > 0 else None
                else:
                    profit_goat_consigned = None
                    return_goat_consigned_pct = None

                if offer_num and stockx_ask_num:
                    profit_stockx_ask = stockx_ask_num - offer_num
                    return_stockx_ask_pct = (profit_stockx_ask / offer_num * 100) if offer_num > 0 else None
                else:
                    profit_stockx_ask = None
                    return_stockx_ask_pct = None

                final_reco = f"BUY AT {item.price_offer}" if item.price_offer else ''

                # Add our new data
                row.update({
                    'quantity': item.quantity,
                    'condition': item.condition,
                    'stockx_bid': item.stockx_bid or '',
                    'stockx_ask': item.stockx_ask or '',
                    'lowest_consigned': item.lowest_consigned or '',
                    'last_consigned_price': item.last_consigned_price or '',
                    'last_consigned_date': item.last_consigned_date or '',
                    'lowest_with_you': item.lowest_with_you or '',
                    'last_with_you_price': item.last_with_you_price or '',
                    'last_with_you_date': item.last_with_you_date or '',
                    'consignment_price': item.consignment_price or '',
                    'ship_to_verify_price': item.ship_to_verify_price or '',
                    'weekly_volume': f"{item.weekly_volume:.2f}" if item.weekly_volume is not None else '',
                    'weekly_volume_prev': f"{item.weekly_volume_prev:.2f}" if item.weekly_volume_prev is not None else '',
                    'price_offer': item.price_offer or '',
                    'offer_reasoning': item.offer_reasoning or '',
                    'final_recommendation': final_reco,
                    'price_offer_numeric': f"{offer_num:.2f}" if offer_num is not None else '',
                    'stockx_bid_numeric': f"{stockx_bid_num:.2f}" if stockx_bid_num is not None else '',
                    'stockx_ask_numeric': f"{stockx_ask_num:.2f}" if stockx_ask_num is not None else '',
                    'goat_ship_to_verify_numeric': f"{goat_ship_num:.2f}" if goat_ship_num is not None else '',
                    'goat_consignment_numeric': f"{goat_consigned_num:.2f}" if goat_consigned_num is not None else '',
                    'goat_absolute_lowest': fmt(goat_abs_lowest) if goat_abs_lowest is not None else '',
                    'last_with_you_price_numeric': f"{last_with_you_price_num:.2f}" if last_with_you_price_num is not None else '',
                    'last_with_you_days_ago': last_with_you_days,
                    'last_consigned_price_numeric': f"{last_consigned_price_num:.2f}" if last_consigned_price_num is not None else '',
                    'last_consigned_days_ago': last_consigned_days,
                    'profit_vs_goat_lowest_gross': f"{profit_goat_lowest:.2f}" if profit_goat_lowest is not None else '',
                    'return_vs_goat_lowest_gross_pct': f"{return_goat_lowest_pct:.1f}%" if return_goat_lowest_pct is not None else '',
                    'profit_vs_goat_consigned_gross': f"{profit_goat_consigned:.2f}" if profit_goat_consigned is not None else '',
                    'return_vs_goat_consigned_gross_pct': f"{return_goat_consigned_pct:.1f}%" if return_goat_consigned_pct is not None else '',
                    'profit_vs_stockx_ask_gross': f"{profit_stockx_ask:.2f}" if profit_stockx_ask is not None else '',
                    'return_vs_stockx_ask_gross_pct': f"{return_stockx_ask_pct:.1f}%" if return_stockx_ask_pct is not None else '',
                    'stockx_sku': item.stockx_sku or '',
                    'stockx_url': item.stockx_url or '',
                    'stockx_size': item.stockx_size or '',
                    'stockx_shoe_name': item.stockx_shoe_name or ''
                })
                
                writer.writerow(row)

    def _looks_like_header_row(self, row: List[str]) -> bool:
        """Check if this row looks like a CSV header"""
        if not row:
            return False
        
        # Common header indicators
        header_words = ['shoe', 'name', 'size', 'price', 'condition', 'brand', 'style', 'sku', 'product']
        first_cell = row[0].lower().strip()
        
        # Check if first cell contains header-like words
        for word in header_words:
            if word in first_cell:
                return True
                
        # Check if row has typical header patterns
        if len(row) >= 2:
            for cell in row[:3]:  # Check first 3 cells
                cell_lower = cell.lower().strip()
                if any(word in cell_lower for word in header_words):
                    return True
                    
        return False

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("📊 Inventory StockX Analyzer")
        print("=" * 40)
        print("Usage:")
        print("  python inventory_stockx_analyzer.py <csv_file>          # Process CSV file")
        print("  python inventory_stockx_analyzer.py --list <text_file>  # Process pasted list")
        print()
        print("Examples:")
        print("  python inventory_stockx_analyzer.py inventory.csv")
        print("  python inventory_stockx_analyzer.py --list my_shoes.txt")
        return

    # Check for pasted list flag
    if len(sys.argv) >= 3 and sys.argv[1] == '--list':
        input_file = sys.argv[2]
        if not Path(input_file).exists():
            print(f"❌ Error: File not found: {input_file}")
            return
            
        analyzer = InventoryStockXAnalyzer()
        try:
            output_file = analyzer.process_pasted_list(input_file)
            print(f"\n🎉 Pasted list analysis complete! Check {output_file} for results.")
        except Exception as e:
            print(f"❌ Error processing pasted list: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        # Regular CSV processing
        input_file = sys.argv[1]
        if not Path(input_file).exists():
            print(f"❌ Error: File not found: {input_file}")
            return

        analyzer = InventoryStockXAnalyzer()
        try:
            output_file = analyzer.process_inventory(input_file)
            print(f"\n🎉 CSV analysis complete! Check {output_file} for results.")
        except Exception as e:
            print(f"❌ Error processing CSV file: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()