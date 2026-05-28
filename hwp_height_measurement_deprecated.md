# ⚠️ HWP Height Measurement - Deprecated

> **Status**: ABANDONED  
> **Date**: 2026-01-20  
> **Reason**: Infinite loop risks, high development cost, low ROI

---

## 📌 Executive Summary

**Decision**: Abandon automatic height measurement of HWP problems in favor of manual line-count adjustment by problem authors.

**Impact**: 
- ✅ System remains fully functional (metadata extraction, test generation still work)
- ❌ No automatic 2-column layout optimization
- ✅ Manual adjustment is simpler and more reliable

---

## 🔴 Why Height Measurement Was Abandoned

### 1. Technical Challenges (Infinite Loops)

**Problem**: HWP COM API is fundamentally unstable when traversing document structure.

**Evidence** (2026-01-20 testing):
```
[Warning] Cursor stuck (1/2) at (0, 261, 29)
[Warning] Cursor stuck (2/2) at (0, 261, 29)
[Warning] Cursor stuck (3/2) at (0, 261, 29)
[Safety] Infinite loop detected! Force terminating...
[Error] HWP initialization failed: (-2147023170, 'RPC server unavailable')
```

**Root Causes**:
- `GetPos()` COM calls fail unpredictably
- Cursor position doesn't advance during footnote traversal
- `GotoFootnote()` action creates circular loops
- HWP process hangs without error messages
- Timeout mechanisms trigger but process remains zombie

**Attempted Solutions** (all failed):
1. ❌ Triple-layer safety (iteration limit, timeout, stuck detection) → Still hung
2. ❌ `taskkill /F /IM Hwp.exe` → Process persists
3. ❌ Pre-cleanup of HWP processes → RPC errors on init
4. ❌ Shorter timeouts (5s, 10s, 20s) → Fails before file opens

### 2. Low Return on Investment

**Development Cost**:
- 3+ iterations of safety mechanisms
- Debugging infinite loops (time-consuming)
- Unpredictable behavior across different HWP files
- Maintenance burden for edge cases

**Actual Value**:
- Only optimizes 2-column layout
- Manual adjustment takes ~30 seconds per problem
- Automated measurement saves ~10 seconds per problem
- **ROI**: Not worth the risk

### 3. Simpler Alternative Exists

**Manual Line Adjustment**:
- Problem authors adjust spacing during creation
- Takes minimal time (already part of authoring workflow)
- No automation risk
- Immediate usability

---

## ✅ What Still Works (HWP Automation Retained)

### Critical Functions NOT Affected

1. **Metadata Extraction** (Phase 1 - Master Indexing)
   - Parse `[학교/연도/단원/난이도]` tags
   - Extract footnote numbers
   - Upload to Firebase
   - **Status**: ✅ Working (PDF-based, no HWP COM needed)

2. **Test Generation** (Phase 3 - Copy/Paste)
   - Open HWP files
   - Copy problem regions (by footnote number)
   - Paste into test template
   - **Status**: ✅ Planned (simple operations, low risk)

### What Was Removed

- ❌ `GetPos()` / `SetPos()` coordinate tracking
- ❌ Height measurement (`HwpUnit` → mm conversion)
- ❌ Automatic column-break calculation
- ❌ Infinite loop prevention mechanisms (no longer needed)

---

## 📋 Revised Workflow

### Problem Authoring (Manual)
```
1. Create problem in HWP
2. Add metadata tag: [학교/연도/단원/난이도]
3. Adjust line spacing to fit 2-column layout (~10-15 lines)
4. Add end marker: □
5. Save file
```

### Test Generation (Automated)
```
1. User selects 20 problems via web dashboard
2. Local program receives request
3. For each problem:
   - Open source HWP file
   - Find footnote number
   - Copy problem region
   - Paste into test template
4. User manually adjusts column breaks if needed
5. Export final test
```

**Key Change**: Step 4 is now manual (previously planned as automatic).

---

## 🔍 Lessons Learned

### HWP COM API Reliability

| Operation | Difficulty | Risk | Decision |
|-----------|-----------|------|----------|
| **Open file** | Low | Low | ✅ Use |
| **Copy/Paste** | Low | Low | ✅ Use |
| **Find text** | Medium | Medium | ✅ Use (with timeout) |
| **Traverse structure** | High | **Critical** | ❌ Avoid |
| **Measure positions** | High | **Critical** | ❌ Avoid |

**Principle**: Stick to simple, stateless operations. Avoid stateful traversal.

### Design Philosophy

> **"Automate the risky, manual the safe"** ❌  
> **"Automate the safe, manual the risky"** ✅

- HWP traversal = risky → manual
- Metadata extraction = safe (PDF-based) → automated
- Copy/paste = safe → automated

---

## 📚 References

- [system_architecture.md](./system_architecture.md) - Full system design (updated)
- [hwp_parser_safe.py](./backend/hwp_parser_safe.py) - Failed prototype (archived)
- [hwp_parser_prototype.py](./backend/hwp_parser_prototype.py) - Initial attempt (archived)

---

## 🔮 Future Reconsideration

**Conditions to revisit height measurement**:
1. HWP releases stable API with guaranteed position tracking
2. Alternative method discovered (e.g., PDF-based height extraction)
3. User demand justifies development cost (>100 hours saved/month)

**Current Status**: Not planned. Manual adjustment is acceptable.

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-20  
**Author**: AnG (Antigravity AI)  
**Approved By**: 상승수학학원
