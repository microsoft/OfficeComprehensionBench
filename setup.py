#!/usr/bin/env python3
"""
Setup script for Claude Document Processor

This script helps set up the environment and dependencies.
"""

import os
import sys
import subprocess
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    return True


def install_dependencies():
    """Install required dependencies."""
    print("Installing dependencies...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✓ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install dependencies: {e}")
        return False


def setup_environment():
    """Set up environment file."""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("✓ .env file already exists")
        return True
    
    if env_example.exists():
        # Copy example to .env
        with open(env_example, 'r') as src, open(env_file, 'w') as dst:
            dst.write(src.read())
        print("✓ Created .env file from example")
        print("  Please edit .env and add your ANTHROPIC_API_KEY")
        return True
    else:
        # Create basic .env file
        with open(env_file, 'w') as f:
            f.write("# Claude Document Processor Environment\n")
            f.write("ANTHROPIC_API_KEY=your_api_key_here\n")
        print("✓ Created basic .env file")
        print("  Please edit .env and add your ANTHROPIC_API_KEY")
        return True


def verify_setup():
    """Verify the setup is working."""
    print("\nVerifying setup...")
    
    # Check if .env file has API key
    try:
        import dotenv
        dotenv.load_dotenv()
        api_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not api_key or api_key == 'your_api_key_here':
            print("⚠ Warning: ANTHROPIC_API_KEY not set in .env file")
            return False
        else:
            print("✓ API key found in environment")
            return True
            
    except ImportError:
        print("✗ python-dotenv not installed")
        return False


def main():
    """Main setup process."""
    print("Claude Document Processor Setup")
    print("=" * 35)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    print("✓ Python version compatible")
    
    # Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Setup environment
    if not setup_environment():
        sys.exit(1)
    
    # Verify setup
    setup_ok = verify_setup()
    
    print("\n" + "=" * 35)
    print("Setup Summary")
    print("=" * 35)
    
    if setup_ok:
        print("✓ Setup completed successfully!")
        print("\nYou can now run:")
        print("  python claude_document_processor.py --help")
    else:
        print("⚠ Setup completed with warnings")
        print("\nPlease:")
        print("1. Edit .env file and add your ANTHROPIC_API_KEY")
        print("2. Run this setup script again to verify")
    
    print("\nExample usage:")
    print("  python claude_document_processor.py \\")
    print("    --document sample.docx \\")
    print("    --questions sample_questions.json")


if __name__ == "__main__":
    main()