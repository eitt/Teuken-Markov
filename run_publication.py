"""Generate English publication figures/tables from the saved analyses, offline."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/"src"))
from americas_markov.publication import main

if __name__=="__main__":
    main(Path(__file__).resolve().parent)
