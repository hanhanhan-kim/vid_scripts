#!/usr/bin/env python3

"""
Batch convert .h264 files to .mp4.
Can output the .mp4 file in monochrome.  
"""

import subprocess
import glob
from os.path import join, splitext, expanduser
import argparse
import cv2


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", 
        help="Absolute path to the root directory.")
    parser.add_argument("framerate", nargs="?", default=30,
        help="Framerate (int)")
    parser.add_argument("-m","--mono", action="store_true",
        help="Convert colour videos to monochrome")
    args = parser.parse_args()

    root = expanduser(args.root)
    framerate = str(args.framerate)
    mono = args.mono
    vids = sorted(glob.glob(join(root, "*.h264")))

    for vid in vids:
        
        output_vid = f"{splitext(vid)[0]}.mp4"

        if not mono:
                
            # Convert:
            args = ["ffmpeg", "-framerate", framerate, "-i", vid, "-c", "copy", output_vid]
            equivalent_cmd = " ".join(args)

            print(f"running command {equivalent_cmd} from dir {root}")
            subprocess.run(args, cwd=root)
        
        else:

            cap = cv2.VideoCapture(vid)

            # Define the codec and create VideoWriter object
            fourcc = cv2.VideoWriter_fourcc(*"mp4v") 
            out = cv2.VideoWriter(filename=output_vid, 
                                  apiPreference=0, 
                                  fourcc=fourcc, 
                                  fps=int(framerate), 
                                  frameSize=(1920,1080), 
                                  params=None)

            while (cap.isOpened()):

                ret, frame = cap.read()

                if ret == True:

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    # In OpenCV, images saved to video file must be three channels:
                    re_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                    # Save:
                    out.write(re_bgr)
                    # Provide live stream:
                    cv2.imshow("live", re_bgr)

                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
                else:
                    break
            
            cap.release()
            out.release()
            cv2.destroyAllWindows()
            

            
if __name__ == "__main__":
    main()