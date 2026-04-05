import pickle, pprint
pkl_path = "DOMZone48_result.pkl"  # TODO: 改成你的实际路径
with open(pkl_path, "rb") as f:
    result = pickle.load(f)
print("result type:", type(result))
if isinstance(result, tuple):
    print("tuple len:", len(result))
    print("tuple[0] type:", type(result[0]))
    print("tuple[1] type:", type(result[1]) if len(result)>1 else None)
    print("bbox_result classes:", len(result[0]) if isinstance(result[0], list) else None)
else:
    print("keys/attrs sample:", dir(result)[:30])

# 打印 bbox_result[0] 的形状信息（如果是 MMDet2.x）
if isinstance(result, tuple) and len(result) >= 1:
    bbox_result = result[0]
    b0 = bbox_result[0]
    print(len(bbox_result))