"""Utility functions for unit conversions and formatting."""


def grams_to_kg(grams: float) -> float:
    """Convert grams to kilograms.
    
    Args:
        grams: Weight in grams
        
    Returns:
        Weight in kilograms
    """
    return grams / 1000.0


def kg_to_grams(kg: float) -> float:
    """Convert kilograms to grams.
    
    Args:
        kg: Weight in kilograms
        
    Returns:
        Weight in grams
    """
    return kg * 1000.0


def format_quantity(quantity: float, unit_type: str) -> str:
    """Format quantity with appropriate unit label.
    
    Args:
        quantity: The quantity value
        unit_type: 'piece', 'kg', or 'g'
        
    Returns:
        Formatted string like "3 pieces", "1.5 kg", "250g"
    """
    if unit_type == "piece":
        if quantity == int(quantity):
            return f"{int(quantity)} piece{'s' if quantity != 1 else ''}"
        return f"{quantity:.2f} pieces"
    elif unit_type == "kg":
        return f"{quantity:.3f} kg"
    elif unit_type == "g":
        # For grams, show as grams if < 1000, otherwise show as kg
        if quantity >= 1000:
            kg = grams_to_kg(quantity)
            return f"{kg:.3f} kg"
        return f"{int(quantity)}g"
    else:
        return f"{quantity:.3f}"


def normalize_to_kg(quantity: float, unit_type: str) -> float:
    """Normalize quantity to kilograms for stock management.
    
    Args:
        quantity: The quantity value
        unit_type: 'piece', 'kg', or 'g'
        
    Returns:
        Quantity in kilograms (for weight-based) or as-is (for pieces)
    """
    if unit_type == "g":
        return grams_to_kg(quantity)
    elif unit_type == "kg":
        return quantity
    else:  # piece
        return quantity  # Pieces are not converted


def calculate_price(quantity: float, unit_type: str, base_unit_price: float) -> float:
    """Calculate total price based on quantity and unit type.
    
    Args:
        quantity: The quantity value
        unit_type: 'piece', 'kg', or 'g'
        base_unit_price: Price per unit (per piece, per kg, or per gram)
        
    Returns:
        Total price
    """
    if unit_type == "g":
        # Convert grams to kg for pricing (base_unit_price is per kg)
        kg = grams_to_kg(quantity)
        return kg * base_unit_price
    elif unit_type == "kg":
        return quantity * base_unit_price
    else:  # piece
        return quantity * base_unit_price

