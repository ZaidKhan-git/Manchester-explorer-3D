"""
Parser for Manchester All Data.json
Extracts and cleans accommodation metadata for processing
"""
import json
import os

def parse_location(location_str):
    """Parse the location JSON string"""
    try:
        return json.loads(location_str)
    except:
        return {}

def parse_school_json(school_str):
    """Parse the school_json string"""
    try:
        return json.loads(school_str)
    except:
        return {}

def parse_supplier_json(supplier_str):
    """Parse the supplier_json string"""
    try:
        return json.loads(supplier_str)
    except:
        return {}

def parse_manchester_data(filepath='Manchester All Data.json'):
    """
    Parse Manchester All Data.json and extract clean accommodation data
    
    Returns:
        list: List of dictionaries with cleaned accommodation data
    """
    print(f"Loading Manchester data from {filepath}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    houses = data.get('data', {}).get('houses', [])
    print(f"Found {len(houses)} accommodations in data file")
    
    accommodations = []
    
    for house in houses:
        # Parse nested JSON strings
        location = parse_location(house.get('location', '{}'))
        school_json = parse_school_json(house.get('school_json', '{}'))
        supplier_json = parse_supplier_json(house.get('supplier_json', '{}'))
        
        # Extract coordinates
        lat = float(house.get('lat') or 0)
        lng = float(house.get('lng') or 0)
        
        # Skip if no valid coordinates
        if lat == 0 or lng == 0:
            print(f"  ⚠️  Skipping {house.get('title', 'Unknown')}: No valid coordinates")
            continue
        
        # Build clean accommodation object
        accommodation = {
            'id': house.get('house_id', '') or '',
            'sku': house.get('sku', '') or '',
            'name': (house.get('title', '') or '').strip(),
            'category': house.get('sub_type_title', 'Student Accommodation') or 'Student Accommodation',
            'address': (house.get('address', '') or '').strip(),
            'lat': lat,
            'lng': lng,
            'zipcode': house.get('zipcode', '') or '',
            
            # Location details
            'location': {
                'lat': lat,
                'lng': lng,
                'address': location.get('address', house.get('address', '')),
                'zipcode': location.get('zipcode', house.get('zipcode', '')),
                'place_id': location.get('place_id', '')
            },
            
            # School/University information
            'school': {
                'name': house.get('school_name', '') or '',
                'unique_name': house.get('school_unique_name', '') or '',
                'distance_km': float(house.get('school_distance') or 0),
                'abbreviation': school_json.get('ab', '') or '',
                'school_id': school_json.get('school_id', '') or ''
            },
            
            # Pricing information
            'pricing': {
                'rent_amount': float(house.get('rent_amount_value') or 0),
                'currency': house.get('rent_amount_abbr', 'GBP') or 'GBP',
                'lease_unit': house.get('lease_unit', 'WEEK') or 'WEEK',
                'min_start_date': house.get('min_start_date', '') or ''
            },
            
            # Property details
            'details': {
                'about': house.get('about', '') or '',
                'bed_num': int(house.get('bed_num') or 0),
                'total_floor': int(house.get('total_floor') or 0),
                'room_type_count': int(house.get('room_type_count') or 0),
                'review_avg_score': float(house.get('review_avg_score') or 0),
                'reviews_count': int(house.get('reviews_count') or 0)
            },
            
            # Supplier information
            'supplier': {
                'name': house.get('supplier_name', '') or supplier_json.get('name', '') or '',
                'logo': supplier_json.get('logo', '') or house.get('supplier_logo', '') or ''
            },
            
            # URLs and media
            'house_url': house.get('house_url', '') or '',
            'media_images': house.get('media_updated_images') or []
        }
        
        accommodations.append(accommodation)
        print(f"  ✓ Parsed: {accommodation['name']} (ID: {accommodation['id']})")
    
    print(f"\n✅ Successfully parsed {len(accommodations)} accommodations")
    return accommodations

if __name__ == '__main__':
    # Test the parser
    accommodations = parse_manchester_data()
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total accommodations: {len(accommodations)}")
    print(f"\nSample accommodation:")
    if accommodations:
        sample = accommodations[0]
        print(f"  Name: {sample['name']}")
        print(f"  Address: {sample['address']}")
        print(f"  Coordinates: ({sample['lat']}, {sample['lng']})")
        print(f"  School: {sample['school']['name']} ({sample['school']['distance_km']} km)")
        print(f"  Price: {sample['pricing']['currency']} {sample['pricing']['rent_amount']}/{sample['pricing']['lease_unit']}")
