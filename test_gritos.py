import requests
import json

BASE_URL = "http://localhost:8000"

def test_mock_endpoint():
    print("Testing /api/mock...")
    response = requests.get(f"{BASE_URL}/api/mock")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Mock Success: {json.dumps(data, indent=2)}")
        return data
    else:
        print(f"❌ Mock Failed: {response.status_code}")
        return None

def test_analyze_endpoint(business_data):
    print("\nTesting /api/analyze...")
    # Add some shocks
    business_data['kak_shock'] = 20
    business_data['rev_shock'] = 10
    
    response = requests.post(f"{BASE_URL}/api/analyze", json=business_data)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Analyze Success: Grit Score: {data['grit_score']}, Runway-decay estimate: {data['runway_decay_estimate']}%")
        print(f"Advice samples: {data['advice']}")
    else:
        try:
            print(f"❌ Analyze Failed: {response.status_code} - {response.json()}")
        except:
            print(f"❌ Analyze Failed: {response.status_code}")

if __name__ == "__main__":
    mock_biz = test_mock_endpoint()
    if mock_biz:
        test_analyze_endpoint(mock_biz)
