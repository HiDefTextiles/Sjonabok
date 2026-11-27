#!/usr/bin/env python3
"""render.py chart.txt out.png [zoom] : black cells on white, grey grid."""
import sys, numpy as np
from PIL import Image
m = np.array([[int(c) for c in l.strip()] for l in open(sys.argv[1]) if l.strip()])
z = int(sys.argv[3]) if len(sys.argv) > 3 else 6
img = np.where(np.kron(m, np.ones((z, z))) > 0, 30, 255).astype(np.uint8)
img[::z, :] = np.minimum(img[::z, :], 200); img[:, ::z] = np.minimum(img[:, ::z], 200)
Image.fromarray(img).save(sys.argv[2])
