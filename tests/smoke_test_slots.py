"""Quick smoke test for SlotRequirement and ClusterSearchRequest."""
import sys
sys.path.insert(0, "apps/api/src")

from edfinder_api.models import SlotRequirement, ClusterSearchRequest

# Test 1: basic economies
s = SlotRequirement(economies=["Refinery", "Industrial"])
assert s.label == "Refinery + Industrial"
assert s.min_score == 65
print(f"OK 1: {s.label}")

# Test 2: archetype_key resolution
s2 = SlotRequirement(archetype_key="refinery_industrial")
assert "Refinery" in s2.economies
assert "Industrial" in s2.economies
assert s2.label == "Refinery Industrial"
print(f"OK 2: {s2.economies} {s2.label}")

# Test 3: Extraction stripped from archetype
s3 = SlotRequirement(archetype_key="extraction_refinery")
assert s3.economies == ["Refinery"]  # Extraction stripped
print(f"OK 3: extraction_refinery -> {s3.economies}")

# Test 4: custom label preserved
s4 = SlotRequirement(archetype_key="refinery_industrial", label="Custom")
assert s4.label == "Custom"
print(f"OK 4: custom label -> {s4.label}")

# Test 5: explicit economies bypass archetype
s5 = SlotRequirement(archetype_key="refinery_industrial", economies=["Agriculture"])
assert s5.economies == ["Agriculture"]
print(f"OK 5: explicit bypass -> {s5.economies}")

# Test 6: empty raises
try:
    SlotRequirement(economies=[])
    assert False
except Exception as e:
    print(f"OK 6: empty raises")

# Test 7: 3+ raises
try:
    SlotRequirement(economies=["A", "B", "C"])
    assert False
except Exception as e:
    print(f"OK 7: 3+ raises")

# Test 8: ClusterSearchRequest with slots
csr = ClusterSearchRequest(slots=[SlotRequirement(archetype_key="refinery_industrial")])
assert len(csr.slots) == 1
print(f"OK 8: CSRequest with slots")

# Test 9: legacy requirements still work
csr2 = ClusterSearchRequest(requirements=[{"economy": "Agriculture", "min_count": 1}])
assert len(csr2.requirements) == 1
print(f"OK 9: CSRequest with legacy requirements")

# Test 10: both raises
try:
    ClusterSearchRequest(
        requirements=[{"economy": "Agriculture"}],
        slots=[SlotRequirement(economies=["Refinery"])],
    )
    assert False
except Exception as e:
    print(f"OK 10: both raises")

print("\nAll tests passed!")
