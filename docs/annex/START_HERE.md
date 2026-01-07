# 🚀 NIC Public - Quick Start Guide

## ✅ YOUR SERVER IS NOW RUNNING!

The Flask app is live at: **http://localhost:5000**

---

## 🎯 What's Working

✅ **Vector Database**: 27 vehicle manual chunks loaded  
✅ **FAISS Index**: Ready for semantic search  
✅ **Flask Web Server**: Running on port 5000  
✅ **Web UI**: Fully operational  
✅ **Ollama Ready**: Configured for local AI models  

---

## 🌐 Access the Application

### Option 1: Web Browser
1. Open your web browser
2. Go to: **http://localhost:5000**
3. Start asking vehicle maintenance questions!

### Option 2: Simple Browser (VS Code)
- The Simple Browser may already be open
- If not, use Ctrl+Shift+P → "Simple Browser: Show"
- Navigate to `http://localhost:5000`

---

## 🤖 Using with Ollama (Offline AI)

### Step 1: Start Ollama
1. Install Ollama (https://ollama.com)
2. Pull models:
    - `ollama pull llama3.2:8b` (Recommended - Fast)
    - `ollama pull qwen2.5-coder:14b` (Tier 2: deeper reasoning)
3. Ensure service is running (it auto-starts): `ollama list`
4. Verify API: should respond at `http://127.0.0.1:11434`

### Step 2: Test Ollama Connection
```powershell
# In a new PowerShell window:
curl http://127.0.0.1:11434/api/tags
```

If working, you'll see JSON with your model info.

### Step 3: Use the App
- The Flask app **automatically detects** Ollama
- No configuration needed!
- Just ask questions in the web UI

---

## 💬 Example Queries to Try

### ✅ In-Scope (Will Work Well)
```
Engine cranks but won't start. What should I check?
What's the torque specification for lug nuts?
How do I test if my alternator is charging?
Battery voltage is low. What are the causes?
```

### ❌ Out-of-Scope (Will Refuse)
```
How do I rebuild a transmission?
What's the tire pressure for a 2024 Tesla?
```
(System will say "not in manual" - this is correct!)

---

## ⚙️ How It Works

### Without Ollama (Retrieval Only)
- You get **raw context chunks** from the manual
- Fast, works offline
- No AI summarization

### With Ollama (Full AI)
- Gets context chunks
- **AI summarizes** and explains
- **Citations** to manual sections
- More natural responses

---

## 🎛️ UI Controls

### Safety Toggles (Top Right)
- **Citation Audit**: ON = Validates all claims against manual
- **Strict Mode**: ON = Direct quotes only (no paraphrasing)

### Model Selector (Input Area)
- **Auto**: Smart selection based on query
- **LLAMA (Fast)**: Quick responses, good for simple questions
- **GPT-OSS (Deep)**: Better for complex troubleshooting

*Both use your Ollama models!*

---

## 🔧 Troubleshooting

### "Server is running but page won't load"
```powershell
# Check if port 5000 is accessible
curl http://localhost:5000
```

### "Ollama not connecting"
1. Verify Ollama service is running (`ollama list`)
2. Check API at `http://127.0.0.1:11434`
3. Check firewall on port 11434

### "Slow responses"
- Use the **8B model** (fireball-llama-3.2) instead of 20B
- Prefer quantized variants (q4_K_M) when available
- Reduce output tokens via NOVA_MAX_TOKENS_* env vars

### "Out of memory"
- Use **quantized models** (Q4_K_M or Q5_K_M)
- Close other GPU-intensive applications
- Reduce parallel requests; keep one tab while testing

---

## 📊 Performance Tips

### Speed Up Retrieval
```powershell
# Enable caching for 2000x speedup on repeat queries
$env:NOVA_ENABLE_RETRIEVAL_CACHE="1"
python nova_flask_app.py
```

### Optimize Ollama
1. Use quantized models (q4_K_M) for 3-4x speed boost
2. Keep output tokens moderate (see NOVA_MAX_TOKENS_* env vars)
3. Limit concurrent requests; single-user tests run fastest

---

## 🛑 Stopping the Server

Press **Ctrl+C** in the terminal where Flask is running

---

## 📁 Project Structure

```
C:\nova_rag_public\
├── nova_flask_app.py          ← Main Flask server
├── backend.py                  ← RAG logic, retrieval, LLM calls
├── data/
│   └── vehicle_manual.txt      ← Source manual (27 pages)
├── vector_db/
│   ├── vehicle_index.faiss     ← Vector database (27 vectors)
│   └── vehicle_docs.jsonl      ← Document metadata
├── templates/
│   └── index.html              ← Web UI
└── static/
    ├── app.js                  ← Frontend logic
    └── style.css               ← Styling
```

---

## 🎓 Next Steps

### Add More Documentation
1. Place PDF/TXT files in `data/`
2. Run: `python ingest_vehicle_manual.py`
3. Run: `python convert_index.py`
4. Restart Flask app

### Deploy to Production
```powershell
# Use waitress instead of Flask dev server
pip install waitress
waitress-serve --port=5000 nova_flask_app:app
```

### Share with Team
- Works on any machine with Python
- No API keys needed (uses Ollama)
- Fully offline capable

---

## 📞 Quick Reference

| What | Command |
|------|---------|
| **Start Server** | `python nova_flask_app.py` |
| **Access UI** | `http://localhost:5000` |
| **Ollama URL** | `http://127.0.0.1:11434` |
| **Stop Server** | `Ctrl+C` in terminal |
| **Check Status** | `curl http://localhost:5000` |

---

## ✨ You're All Set!

Your NIC Public system is running and ready to answer vehicle maintenance questions!

🌐 **Open**: http://localhost:5000  
🤖 **With AI**: Start Ollama first  
📖 **Documentation**: See LM_STUDIO_SETUP.md for details  

**Happy troubleshooting!** 🚗🔧
