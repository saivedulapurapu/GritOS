# GritOS: Intelligent Operational & Financial Analytics

GritOS is an operational and financial analysis platform purpose-built to help businesses monitor their financial health, evaluate risks, and navigate unpredictable market conditions with confidence. 

At its core is the **Shock Engine**, a dynamic stress-testing module. Users can simulate adverse scenarios—like unexpected revenue drops, spikes in Customer Acquisition Cost (CAC), or rising Cost of Goods Sold (COGS). This allows founders to instantly visualize the impact on their bottom line and runway.

GritOS also features a **Capital Lock Index** that calculates the exact amount of capital trapped in unsold inventory. It provides warnings when stock turnover slows to dangerous levels, helping operators make proactive decisions before cash flow dries up.

Furthermore, GritOS integrates Large Language Models (via Groq) to analyze these financial metrics, acting as an AI-powered financial advisor. It offers personalized, data-driven recommendations on cost-cutting and growth. Built with Next.js, Tailwind CSS, and a powerful Python backend, GritOS is the ultimate operating system for mitigating business risk.

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Node.js (v16+)
- Groq API Key

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/saivedulapurapu/GritOS.git
   cd GritOS
   ```

2. **Setup the Backend:**
   ```bash
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   *Note: Create a `.env` file in the `backend/` directory and add your Groq API Key (`GROQ_API_KEY=your_key_here`).*

3. **Setup the Frontend:**
   ```bash
   cd ../frontend
   npm install
   ```

## 🛠️ How to Run

To launch both the FastAPI backend and Next.js frontend simultaneously, you can use the provided PowerShell script from the root directory:

```powershell
.\run_gritos.ps1
```

Alternatively, you can run them manually:
- **Backend:** `cd backend` -> `.\.venv\Scripts\Activate.ps1` -> `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- **Frontend:** `cd frontend` -> `npm run dev`
