# 🚀 NIC Public - Quick Start Guide

## ✅ YOUR SERVER IS NOW RUNNING!

The Flask app is live at: **http://localhost:5000**

---

## 🎯 What's Working

✅ **Vector Database**: 27 vehicle manual chunks loaded  
✅ **FAISS Index**: Ready for semantic search  
✅ **Flask Web Server**: Running on port 5000  
✅ **Web UI**: Fully operational  
✅ **LM Studio Ready**: Configured for local AI models  

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

## 🤖 Using with LM Studio (Offline AI)

### Step 1: Start LM Studio Server
1. Open **LM Studio** application
2. Go to **"Local Server"** tab (left sidebar)
3. Load your model:
   - `fireball-meta-llama-3.2-8b-instruct-agent-003-128k-code-dpo` (Recommended - Fast)
   - OR `qwen/qwen2.5-coder-14b` (Tier 2: deeper reasoning, ~5-10s per query)
4. Click **"Start Server"**
5. Verify it shows: `Server running on http://127.0.0.1:1234`

### Step 2: Test LM Studio Connection
```powershell
# In a new PowerShell window:
curl http://127.0.0.1:1234/v1/models
```

If working, you'll see JSON with your model info.

### Step 3: Use the App
- The Flask app **automatically detects** LM Studio
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

### Without LM Studio (Retrieval Only)
- You get **raw context chunks** from the manual
- Fast, works offline
- No AI summarization

### With LM Studio (Full AI)
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

*Both use your LM Studio models!*

---

## 🔧 Troubleshooting

### "Server is running but page won't load"
```powershell
# Check if port 5000 is accessible
curl http://localhost:5000
```

### "LM Studio not connecting"
1. Verify LM Studio server is running (`http://127.0.0.1:1234`)
2. Check for firewall blocking port 1234
3. Try restarting LM Studio server

### "Slow responses"
- Use the **8B model** (fireball-llama-3.2) instead of 20B
- Enable **GPU offload** in LM Studio settings
- Reduce **Context Length** to 4096 in LM Studio

### "Out of memory"
- Use **quantized models** (Q4_K_M or Q5_K_M)
- Close other GPU-intensive applications
- Reduce batch size in LM Studio

---

## 📊 Performance Tips

### Speed Up Retrieval
```powershell
# Enable caching for 2000x speedup on repeat queries
$env:NOVA_ENABLE_RETRIEVAL_CACHE="1"
python nova_flask_app.py
```

### Optimize LM Studio
1. Settings → **GPU Offload** → Set to maximum (or adjust for VRAM)
2. Context Length → **4096** (faster) or **8192** (better quality)
3. Use **Q4_K_M** quantized models for 3-4x speed boost

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
- No API keys needed (uses LM Studio)
- Fully offline capable

---

## 📞 Quick Reference

| What | Command |
|------|---------|
| **Start Server** | `python nova_flask_app.py` |
| **Access UI** | `http://localhost:5000` |
| **LM Studio URL** | `http://127.0.0.1:1234` |
| **Stop Server** | `Ctrl+C` in terminal |
| **Check Status** | `curl http://localhost:5000` |

---

## ✨ You're All Set!

Your NIC Public system is running and ready to answer vehicle maintenance questions!

🌐 **Open**: http://localhost:5000  
🤖 **With AI**: Start LM Studio first  
📖 **Documentation**: See LM_STUDIO_SETUP.md for details  

**Happy troubleshooting!** 🚗🔧
