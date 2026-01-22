"""
Extract technical terms from multi-domain PDFs to extend GAR glossary.
"""

import json
from pathlib import Path
from collections import defaultdict
import re

def extract_technical_terms():
    """
    Extract domain-specific technical terms from the indexed manuals.
    Returns a dictionary of new glossary entries.
    """
    
    # Equipment and military-specific terms to add to GAR
    new_glossary_entries = {
        # Military vehicle terms (from TM9-802 - GMC DUKW amphibian truck)
        "amphibian_vehicle": {
            "amphibian mode": ["water operation", "water crossing", "ford", "fording", "water travel", "marine operation"],
            "dukw": ["duck", "amphibian truck", "gmc 353", "6x6 amphibian"],
            "bilge pump": ["water pump", "drain pump", "hull pump"],
            "propeller": ["marine propeller", "water propulsion", "screw"],
            "rudder": ["water steering", "marine steering"],
            "freeboard": ["waterline clearance", "hull clearance"],
            "bow": ["front", "prow", "forward section"],
            "stern": ["rear", "aft", "back section"],
            "ford": ["water crossing", "river crossing", "water traverse"],
            "tm9": ["technical manual 9", "army technical manual"]
        },
        
        # Forklift/Material handling (from TM-10-3930 - ATLAS)
        "forklift": {
            "atlas": ["all terrain lifter", "army system", "military forklift"],
            "lift capacity": ["load rating", "weight capacity", "maximum load", "rated capacity"],
            "forks": ["lift forks", "fork tines", "tynes"],
            "mast": ["lift mast", "carriage mast", "fork carriage"],
            "hydraulic": ["hydraulic system", "hydraulic pressure", "hydraulic circuit"],
            "load center": ["center of gravity", "load cog", "balance point"],
            "tilt": ["fork tilt", "mast tilt", "forward tilt", "backward tilt"],
            "reach": ["fork reach", "extension", "telescoping"],
            "overhead guard": ["safety cage", "operator protection", "roll cage"],
            "counterweight": ["balance weight", "rear weight"],
            "tm10": ["technical manual 10", "quartermaster manual"]
        },
        
        # HVAC (from Carrier manual)
        "hvac": {
            "ductless": ["mini-split", "wall mount", "split system"],
            "heat pump": ["reverse cycle", "cooling and heating", "dual mode"],
            "refrigerant": ["coolant", "freon", "r-410a", "refrigerant gas"],
            "compressor": ["refrigerant compressor", "hvac compressor"],
            "evaporator": ["indoor coil", "cooling coil", "evap coil"],
            "condenser": ["outdoor coil", "condenser coil", "condensing unit"],
            "expansion valve": ["txv", "metering device"],
            "btu": ["british thermal unit", "cooling capacity", "heating capacity"],
            "seer": ["seasonal energy efficiency ratio", "efficiency rating"],
            "thermostat": ["temperature control", "room controller", "temp sensor"],
            "air handler": ["indoor unit", "blower unit", "fan coil"]
        },
        
        # Radar/Aviation (from WXR-2100)
        "radar": {
            "wxr": ["weather radar", "wx radar", "weather detection"],
            "multiscan": ["multi-scan", "automatic scanning", "vertical scan"],
            "reflectivity": ["radar return", "echo strength", "signal strength"],
            "precipitation": ["rain", "weather", "moisture", "convective activity"],
            "turbulence": ["turb", "rough air", "convection", "wind shear"],
            "gain": ["receiver gain", "sensitivity", "signal amplification"],
            "tilt": ["antenna tilt", "scan angle", "elevation angle"],
            "range": ["detection range", "radar range", "maximum range"],
            "bearing": ["azimuth", "direction", "heading"],
            "sweep": ["scan", "antenna rotation", "radar sweep"],
            "target": ["return", "echo", "contact", "detection"]
        },
        
        # General military/equipment terms
        "military": {
            "tm": ["technical manual", "army manual", "field manual"],
            "nsn": ["national stock number", "part number", "supply number"],
            "mos": ["military occupational specialty", "job code"],
            "depot": ["maintenance depot", "repair facility"],
            "pmcs": ["preventive maintenance checks", "pre-operation checks"],
            "lubrication order": ["lube order", "lubrication schedule", "lo"],
            "torque spec": ["torque specification", "tightening torque", "bolt torque"],
            "clearance": ["tolerance", "gap", "spacing"]
        }
    }
    
    return new_glossary_entries


def extend_glossary():
    """Extend the automotive glossary with multi-domain terms."""
    glossary_path = Path("data/automotive_glossary.json")
    
    # Load existing glossary
    with open(glossary_path, 'r', encoding='utf-8') as f:
        glossary = json.load(f)
    
    # Get new terms
    new_terms = extract_technical_terms()
    
    # Merge new terms
    for category, terms in new_terms.items():
        if category not in glossary:
            glossary[category] = {}
        glossary[category].update(terms)
    
    # Update version and metadata
    glossary["_version"] = "2.0 - Multi-Domain"
    glossary["_domains"] = ["automotive", "military_vehicle", "forklift", "hvac", "radar"]
    glossary["_last_updated"] = "2026-01-21"
    
    # Save extended glossary
    backup_path = Path("data/automotive_glossary_v1_backup.json")
    if not backup_path.exists():
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(glossary, f, indent=2, ensure_ascii=False)
        print(f"✅ Backed up original glossary to {backup_path}")
    
    with open(glossary_path, 'w', encoding='utf-8') as f:
        json.dump(glossary, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Extended glossary saved to {glossary_path}")
    print(f"   Added {len(new_terms)} new categories")
    print(f"   Total categories: {len([k for k in glossary.keys() if not k.startswith('_')])}")
    
    # Print summary
    print("\n" + "="*70)
    print("NEW GLOSSARY CATEGORIES")
    print("="*70)
    for category in new_terms.keys():
        term_count = len(new_terms[category])
        print(f"  {category:20s}: {term_count:3d} term mappings")
    
    return glossary


if __name__ == "__main__":
    glossary = extend_glossary()
