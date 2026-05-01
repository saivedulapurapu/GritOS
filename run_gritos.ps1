Write-Host "🚀 Starting GritOS Survival Intelligence Engine..." -ForegroundColor Cyan

# Start Backend in a new process
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; .\.venv\Scripts\Activate.ps1; uvicorn main:app --reload --host 0.0.0.0 --port 8000"
Write-Host "✅ Backend API starting on http://localhost:8000" -ForegroundColor Green

# Start Frontend in current process
Write-Host "✅ Frontend starting on http://localhost:3000" -ForegroundColor Green
cd frontend
npm run dev
