#!/usr/bin/env python3
"""Run NIC with Waitress WSGI server instead of Flask dev server.

Waitress is production-grade and handles concurrent requests better than Flask's
development server. This avoids the LLM context loading crash we see with Flask dev.

Usage:
    python run_waitress.py [--port 5000] [--threads 4]
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    parser = argparse.ArgumentParser(description="Run NIC with Waitress WSGI server")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--threads", type=int, default=4, help="Number of worker threads (default: 4)")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds (default: 120)")
    
    args = parser.parse_args()
    
    # Import Flask app
    from nova_flask_app import app
    
    # Ensure we're using production settings
    app.config["DEBUG"] = False
    app.config["ENV"] = "production"
    
    print("\n" + "=" * 80)
    print(f"Starting NIC with Waitress WSGI server")
    print("=" * 80)
    print(f"Host:        {args.host}")
    print(f"Port:        {args.port}")
    print(f"Threads:     {args.threads}")
    print(f"Timeout:     {args.timeout}s")
    print("=" * 80)
    print(f"Access at:   http://{args.host}:{args.port}")
    print("=" * 80 + "\n")
    
    try:
        from waitress import serve
        
        # Serve with Waitress instead of Flask dev server
        serve(
            app,
            host=args.host,
            port=args.port,
            threads=args.threads,
            connection_limit=1000,
            recv_bytes=8192,
            send_bytes=8192,
            cleanup_interval=30,
            channel_timeout=args.timeout,
            _quiet=False,
        )
    except ImportError:
        print("\n❌ Waitress not installed. Install with:")
        print("   pip install waitress")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
