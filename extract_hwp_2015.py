# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pyhwpx
hwp = pyhwpx.Hwp(visible=False)
hwp.open("G:/문제은행/문제은행2/내기왕-단원분류표-2015개정교과.hwp")
hwp.save_as("G:/문제은행/문제은행2/단원분류표-2015.txt", format="TEXT")
hwp.quit()
print("[DONE]")
