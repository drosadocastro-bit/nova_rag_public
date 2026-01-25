# Phase 3 Corpus Sourcing Research

**Task:** Identify public-domain technical documentation sources  
**Date:** January 22, 2026  
**Status:** Research phase

---

## Selection Criteria

### Must-Have Requirements
1. ✅ **Public Domain / Open License** - No copyright restrictions
2. ✅ **Safety-Critical Domain** - Vehicle maintenance, hardware operation, safety standards
3. ✅ **Technical Content** - Procedures, diagnostics, troubleshooting
4. ✅ **Air-Gap Compatible** - Downloadable for offline use
5. ✅ **Non-Sensitive** - No classified, ITAR, or export-controlled content

### Nice-to-Have
- Multiple formats (PDF, HTML, plain text)
- Well-structured with TOCs, sections
- Diagrams and schematics
- 50+ pages per manual (generates 100-500 chunks)

---

## Source Category 1: Vehicle Service Manuals

### Internet Archive - Public Domain Vehicle Manuals

**URL:** https://archive.org/details/texts?query=vehicle+service+manual

**Key Collections:**
1. **Pre-1928 Vehicle Manuals** (Public Domain)
   - Ford Model T service guides
   - Early automotive repair procedures
   - Maintenance schedules, troubleshooting

2. **Government Publications** (Public Domain)
   - U.S. Army vehicle TMs (Technical Manuals)
   - Public-release military maintenance guides
   - Pre-1980s civilian vehicle manuals

**Specific Candidates:**
- **Ford Model T Shop Manual (1925)**
  - URL: `archive.org/details/FordModelTShopManual`
  - Format: PDF, 200+ pages
  - Content: Engine repair, transmission, electrical system
  - License: Public domain (pre-1928)

- **U.S. Army TM 9-803 (Jeep Maintenance)**
  - URL: `archive.org/details/TM9803`
  - Format: PDF, 350+ pages
  - Content: Complete maintenance procedures
  - License: U.S. Government work (public domain)

- **Volkswagen Beetle Repair Manual (pre-1978)**
  - Available in public domain collections
  - Comprehensive maintenance procedures
  - International availability

**Validation Steps:**
1. Verify publication date (pre-1928 or government work)
2. Check licensing terms
3. Download sample (test PDF extraction)
4. Estimate chunk count (50 pages ≈ 100-200 chunks)

---

## Source Category 2: Open-Source Hardware Documentation

### Arduino Official Documentation

**URL:** https://docs.arduino.cc/ and https://github.com/arduino

**License:** Creative Commons Attribution-ShareAlike 3.0  
**Content Type:** Technical reference, tutorials, schematics

**Specific Resources:**
1. **Arduino Hardware Documentation**
   - Board schematics and datasheets
   - Pin configurations
   - Electrical specifications
   - Available as HTML/PDF

2. **Arduino Language Reference**
   - Function documentation
   - Code examples
   - Troubleshooting guides

**Format:** Primarily HTML, easily scrapable with BeautifulSoup4

---

### Raspberry Pi Foundation Documentation

**URL:** https://www.raspberrypi.com/documentation/

**License:** Creative Commons (varies by section)  
**Content Type:** Hardware guides, OS documentation, troubleshooting

**Specific Resources:**
1. **Raspberry Pi Hardware Documentation**
   - GPIO pinout guides
   - Hardware specifications
   - Power requirements
   - Available as PDF/HTML

2. **Raspberry Pi OS Documentation**
   - Configuration guides
   - Troubleshooting procedures
   - System administration

**Format:** HTML with downloadable PDFs

---

### OpenPLC Project Documentation

**URL:** https://www.openplcproject.com/reference/

**License:** GPL/Open Documentation  
**Content Type:** Industrial control systems, ladder logic, safety procedures

**Specific Resources:**
- PLC programming guides
- Industrial automation procedures
- Safety interlocks and fault handling
- Suitable for safety-critical domain validation

---

## Source Category 3: Open Safety Standards

### NFPA (National Fire Protection Association) - Free Access Standards

**URL:** https://www.nfpa.org/codes-and-standards/free-access

**License:** Free access (not public domain, but freely readable)  
**Content Type:** Fire safety, electrical safety codes

**Specific Standards (Free Access):**
- NFPA 70 (National Electrical Code) - Selected sections
- NFPA 101 (Life Safety Code) - Public excerpts
- Fire safety procedures and equipment standards

**Note:** Check terms - some sections free for reading, download restrictions may apply

---

### ANSI (American National Standards Institute) - Public Previews

**URL:** https://webstore.ansi.org/

**Publicly Available:**
- Standards previews (first 10-20 pages)
- ISO publicly available standards
- Free technical reports

**Alternative:** **ISO Freely Available Standards**
- URL: https://www.iso.org/iso-standards-and-patents.html
- ~1,000 standards available free
- Safety, quality, technical specifications

---

### SAE (Society of Automotive Engineers) - Open Access Papers

**URL:** https://www.sae.org/publications/technical-papers/open-access

**License:** Open Access (varies)  
**Content Type:** Automotive engineering, safety standards, testing procedures

**Topics:**
- Vehicle diagnostics
- Safety systems (ABS, airbags)
- Emissions and testing procedures

---

## Source Category 4: Government Technical Publications

### NASA Technical Reports Server (NTRS)

**URL:** https://ntrs.nasa.gov/

**License:** Public domain (U.S. Government work)  
**Content Type:** Engineering procedures, safety protocols, testing documentation

**Relevant Collections:**
- Spacecraft maintenance procedures
- Safety protocols and fault handling
- Engineering best practices
- Quality control procedures

**Suitable For:** Safety-critical systems validation

---

### NIST (National Institute of Standards and Technology)

**URL:** https://www.nist.gov/publications

**License:** Public domain (U.S. Government)  
**Content Type:** Standards, measurement procedures, reference data

**Specific Publications:**
- NIST Handbooks (technical procedures)
- Special Publications (cybersecurity, safety)
- Engineering standards and testing

---

### U.S. Military Technical Manuals (Declassified)

**URL:** https://www.everyspec.com/

**License:** Public domain (government work)  
**Content Type:** Equipment maintenance, operation, troubleshooting

**Collections:**
- Vehicle TMs (Technical Manuals)
- Equipment operator guides
- Maintenance procedures
- Safety protocols

**Examples:**
- TM 9-2320 series (vehicle maintenance)
- TM 5-4200 series (construction equipment)
- Non-classified, maintenance-focused content

---

## Recommended Phase 3 Corpus Mix

### Tier 1: High Priority (Download First)

| Source | Type | Est. Chunks | License | Priority |
|--------|------|-------------|---------|----------|
| **U.S. Army Jeep TM 9-803** | Vehicle Manual | 500-800 | Public Domain | ⭐⭐⭐ |
| **Ford Model T Manual** | Vehicle Manual | 300-500 | Public Domain | ⭐⭐⭐ |
| **Arduino Hardware Docs** | Open Hardware | 200-400 | CC BY-SA 3.0 | ⭐⭐⭐ |
| **Raspberry Pi GPIO Guide** | Open Hardware | 100-200 | CC BY-SA 4.0 | ⭐⭐ |

**Total Tier 1:** ~1,100-1,900 chunks

---

### Tier 2: Secondary (Expand After Validation)

| Source | Type | Est. Chunks | License | Priority |
|--------|------|-------------|---------|----------|
| **NASA Safety Procedures** | Government | 300-600 | Public Domain | ⭐⭐ |
| **OpenPLC Documentation** | Industrial Control | 200-400 | GPL/Open | ⭐⭐ |
| **NIST Handbooks** | Standards | 400-800 | Public Domain | ⭐ |
| **SAE Open Papers** | Automotive | 200-400 | Open Access | ⭐ |

**Total Tier 2:** ~1,100-2,200 chunks

---

## Download Strategy

### Phase 1: Validation Set (5-10 documents)
**Goal:** Test incremental indexing, validate quality

1. Download 2-3 vehicle manuals (TM 9-803, Model T)
2. Download 2-3 hardware guides (Arduino, RPi)
3. Download 1-2 safety standards (NASA, NIST)

**Expected Output:** 1,000-1,500 chunks

---

### Phase 2: Production Set (20-50 documents)
**Goal:** Reach 10k-50k chunk target, stress-test scalability

1. Expand vehicle manuals (10-15 additional TMs)
2. Complete Arduino/RPi documentation
3. Add industrial control docs (OpenPLC)
4. Include NIST/NASA safety procedures

**Expected Output:** 10,000-50,000 chunks

---

## Legal Compliance Checklist

### Before Download
- [ ] Verify publication date (pre-1928 = public domain)
- [ ] Check license terms (CC, GPL, government work)
- [ ] Confirm no export control / ITAR restrictions
- [ ] Document source URL and license

### After Download
- [ ] Store license file with manual
- [ ] Record attribution requirements
- [ ] Tag with domain (vehicle, hardware, safety)
- [ ] Validate file integrity (SHA-256)

---

## Next Steps (Task 8)

1. **Download Tier 1 sources** (5 manuals)
2. **Validate format** (PDF extraction, HTML parsing)
3. **Test ingestion** (chunk count, quality)
4. **Verify licensing** (screenshot license terms)
5. **Document corpus** (manifest with sources)

---

## Known Challenges

### Challenge 1: PDF Quality
**Issue:** Scanned PDFs may have poor OCR  
**Solution:** Test with `pdfplumber`, fall back to `pytesseract`

### Challenge 2: HTML Formatting
**Issue:** Inconsistent HTML structure  
**Solution:** Use BeautifulSoup4 with robust parsing (already implemented in Phase 2.5)

### Challenge 3: License Ambiguity
**Issue:** Some sources unclear on commercial use  
**Solution:** Focus on clearly public-domain sources (pre-1928, government)

---

## Success Metrics

| Metric | Target | Validation |
|--------|--------|------------|
| **Total Documents** | 5-10 | ✅ Tier 1 list ready |
| **Total Chunks** | 1,000+ | ✅ Estimated 1,100-1,900 |
| **License Clarity** | 100% | ✅ All public domain or open |
| **Domain Coverage** | 3+ domains | ✅ Vehicle, hardware, safety |
| **Format Diversity** | PDF + HTML | ✅ Both formats included |

---

**Status:** Ready to proceed to Task 8 (Download & Validation) ✅

---

*Generated: January 22, 2026*  
*NIC Phase 3 Corpus Research*
