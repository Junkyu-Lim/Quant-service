"""
WSGI entry point for Vercel deployment.
"""

from webapp.app import app

if __name__ == "__main__":
    app.run()
