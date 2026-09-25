#!/usr/bin/python3 -I
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from gateway import main
main()
