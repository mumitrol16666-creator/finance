from aiogram import F

# Create the filter
magic_filter = F.data.startswith("rp:") & (F.data != "rp:export")

# Test values
val_match = "rp:view:month"
val_export = "rp:export"

# In aiogram, magic filters are callable and resolve values against an object or dict
# MagicFilter uses resolve_field or similar, but we can call it on a mock object
class MockCallbackQuery:
    def __init__(self, data):
        self.data = data

mock_match = MockCallbackQuery(val_match)
mock_export = MockCallbackQuery(val_export)

res_match = magic_filter.resolve(mock_match)
res_export = magic_filter.resolve(mock_export)

print(f"Filter result for '{val_match}': {res_match}")
print(f"Filter result for '{val_export}': {res_export}")

assert res_match == True, "Should match rp:view:month"
assert res_export == False, "Should NOT match rp:export"
print("✅ Aiogram filter evaluation test passed!")
