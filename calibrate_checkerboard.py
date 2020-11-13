#!/usr/bin/env python3

"""
Undistorts videos by calibrating a checkerboard .mp4 video or a 
folder of checkerboard .jpg images. 
The number of internal corners on the checkerboard's rows and columns 
are interchangeable. 
"""

import subprocess
import argparse
import pickle
from os.path import splitext, expanduser, basename, dirname
from os import path, mkdir
from pathlib import Path
from shutil import rmtree
from sys import exit

import cv2
import numpy as np
from tqdm import tqdm, trange


def convert_vid_to_jpgs(vid, framerate, backend="opencv"):

    """
    Converts a .mp4 video into a folder of .jpgs. 
    Saves the .jpgs folder into the same directory as the input .mp4 video.

    Parameters:
    -----------
    vid (str): Path to .mp4 video 
    framerate (int): Framerate with which `vid` was recorded.
    backend (str): Backend with which to convert. Can be either "opencv" or "ffmpeg".
        Default is "opencv". The ffmpeg backend is much faster, but is poor quality.

    Returns:
    --------
    A folder of .jpgs.
    """

    assert(".mp4" in vid), f"'{basename(vid)}' is not in {dirname(vid)}"
    assert(backend=="opencv" or backend=="ffmpeg"), "Must specify the backend as 'opencv' or 'ffmpeg'"

    vid = expanduser(vid)
    jpgs_dir = path.join(dirname(vid), f"{basename(splitext(vid)[0])}")

    if Path(jpgs_dir).is_dir():

        print(f"{basename(jpgs_dir)} already exists at '{dirname(jpgs_dir)}'. Skipping ...")

    else:
        
        mkdir(jpgs_dir)
        print(f"Converting '{basename(vid)}' to .jpgs ...")

        if backend=="opencv": 

            cap = cv2.VideoCapture(vid)
            
            i = 0
            while (cap.isOpened()):

                ret, frame = cap.read()

                if ret == True:

                    cv2.imwrite(path.join(jpgs_dir, f"frame_{i:08d}.jpg"), frame)
                    cv2.imshow(f"converting {basename(vid)} ...", frame) 

                    i += 1

                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                else:
                    break
            
            cap.release()
            cv2.destroyAllWindows()

        elif backend=="ffmpeg":

            args = ["ffmpeg", "-i", vid, "-vf", f"fps={str(framerate)}", "frame_%08d.jpg"]
            equivalent_cmd = " ".join(args)

            print(f"running command {equivalent_cmd} from {jpgs_dir}")
            subprocess.run(args, cwd=jpgs_dir)


def calibrate_checkerboard(board_vid, m_corners, n_corners, framerate=30, do_debug=True):

    """
    Finds internal corners of checkerboards to generate the camera matrix.

    Parameters:
    -----------
    board_vid (str): Path to .mp4 checkerboard video or path to a folder containing 
        checkerboard .jpgs.
    m_corners (int): Number of internal corners along the rows of the checkerboard
    n_corners (int): Number of internal corners along the columns of the checkerboard
    framerate (int): Framerate with which `board_vid` was recorded
    do_debug (bool): If True, will show a live feed of the labelled checkerboards, and
        will save a directory of the labelled checkerboard .jpgs. Default is True. 

    Returns:
    --------
    A dictionary of length 6 that consists of ret, cam_mtx, dist, r_vecs, t_vecs 
    from cv2.calibrateCamera() and the mean reprojection error. Saves this dictionary as
    a pickle file called 'cam_calib_results.pkl'. If this file already exists, running
    this function will read the pickle file and return the contained dictionary. 
    In addition, saves at least a video of the labelled checkerboards.
    """
    
    assert(basename(board_vid) != "checkerboards.mp4"), "Rename 'checkerboards.mp4' to something else!"

    if Path(board_vid).is_file():
        assert(splitext(board_vid)[1] == ".mp4"), "`board_vid` must be an '.mp4' file!"

    output_vid = path.join(dirname(board_vid), "checkerboards.mp4")

    if do_debug:

        # TODO: use raw_input for the below print message:
        print("Debug mode is on, which means the script will actually delete things. Previous checkerboard outputs will be deleted ...")
        boards_dir = path.join(dirname(board_vid), "checkerboards")

        if Path(boards_dir).is_dir():
            rmtree(boards_dir)
        else:
            mkdir(boards_dir)

        if Path(output_vid).is_file():
            Path(output_vid).unlink()

    pkl_file = path.join(dirname(board_vid), "cam_calib_results.pkl")

    if Path(output_vid).is_file() and Path(pkl_file).is_file():
        
        print(f"{basename(output_vid)} already exists at {dirname(output_vid)}")
        print(f"reading {basename(pkl_file)} from {dirname(pkl_file)} ...")
        cam_calib_results = pickle.load(open(pkl_file, "rb")) 
        msg = f"camera matrix: \n{cam_calib_results['cam_mtx']}\n\ndistance coefficients: \n{cam_calib_results['dist']}\n\nmean reprojection error: \n{cam_calib_results['mean_reproj_error']}"
        print(msg)

        return cam_calib_results

    elif not Path(output_vid).is_file() and not Path(pkl_file).is_file():

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*"mp4v") 
        out = cv2.VideoWriter(filename=output_vid, 
                              apiPreference=0, 
                              fourcc=fourcc, 
                              fps=int(framerate), 
                              frameSize=(1920,1080), # TODO: make this a kwarg?
                              params=None) 

        # FIND CORNERS:

        # Termination criteria:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

        # Prepare object points like (0,0,0), (1,0,0), (2,0,0) ....,(6,5,0):
        obj_p = np.zeros((n_corners * m_corners, 3), np.float32)
        obj_p[:,:2] = np.mgrid[0:m_corners, 0:n_corners].T.reshape(-1,2)

        # Arrays to store object points and image points from all the images: 
        obj_points = [] # 3d point in real world space
        img_points = [] # 2d points in image plane

        i = 0

        if Path(board_vid).is_file():

            cap = cv2.VideoCapture(board_vid)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            pbar = trange(frame_count)
            
            for _ in pbar:
                
                ret, frame = cap.read()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Find the chess board corners:
                ret, corners = cv2.findChessboardCorners(gray, (m_corners, n_corners), None)

                # If found, add object points, image points (after refining them):
                if ret == True:
                    
                    obj_points.append(obj_p)

                    # This method increases the accuracy of the identified corners:
                    better_corners = cv2.cornerSubPix(gray, corners, (11,11), (-1,-1), criteria)
                    img_points.append(better_corners)

                    # Draw and display the corners:
                    img = cv2.drawChessboardCorners(frame, (m_corners, n_corners), better_corners, ret)
                    
                    # Save to video:
                    out.write(img)

                    if do_debug:

                        cv2.imwrite(path.join(boards_dir, f"frame_{i:08d}.jpg"), img)
                        cv2.imshow("checkerboard detected ...", img) 
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
                    
                    pbar.set_description(f"found {i+1} checkerboards from {frame_count} frames") 
                    cv2.waitKey(1) 
                    i += 1

            cap.release()
        
        elif Path(board_vid).is_dir():

            jpgs = [str(path.absolute()) for path in Path(board_vid).rglob("*.jpg")]
            pbar = tqdm(jpgs)
            
            for jpg in pbar:

                img = cv2.imread(jpg)
                gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)

                # Find the chess board corners:
                ret, corners = cv2.findChessboardCorners(gray, (m_corners, n_corners),None)

                # If found, add object points, image points (after refining them):
                if ret == True:
                    
                    obj_points.append(obj_p)

                    # This method increases the accuracy of the identified corners:
                    better_corners = cv2.cornerSubPix(gray, corners, (11,11), (-1,-1), criteria)
                    img_points.append(better_corners)

                    # Draw and display the corners:
                    img = cv2.drawChessboardCorners(img, (m_corners, n_corners), better_corners, ret)
                    
                    # Save to video:
                    out.write(img)

                    if do_debug:

                        cv2.imwrite(path.join(boards_dir, basename(jpg)), img)
                        cv2.imshow("checkerboard detected ...", img) 
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
                    
                    pbar.set_description(f"found {i+1} checkerboards from {len(jpgs)} frames") 
                    cv2.waitKey(1) 
                    i += 1
        
        out.release
        cv2.destroyAllWindows()

        # CALIBRATE: 
        ret, cam_mtx, dist, r_vecs, t_vecs = cv2.calibrateCamera(obj_points, img_points, 
                                                                 gray.shape[::-1], 
                                                                 None, None)

        # Get re-projection error: 
        total_reproj_error = 0
        for obj_point, img_point, r_vec, t_vec in zip(obj_points, img_points, r_vecs, t_vecs):

            img_points_2, _ = cv2.projectPoints(obj_point, r_vec, t_vec, cam_mtx, dist)
            error = cv2.norm(img_point, img_points_2, cv2.NORM_L2) / len(img_points_2)
            total_reproj_error += np.abs(error)

        mean_reproj_error = total_reproj_error / len(obj_points)

        # Output:
        msg = f"camera matrix: \n{cam_mtx}\n\ndistance coefficients: \n{dist}\n\nmean reprojection error: \n{mean_reproj_error}"
        print(msg)

        cam_calib_results = {"ret": ret, "cam_mtx": cam_mtx, "dist": dist, "r_vecs": r_vecs, "t_vecs": t_vecs, "mean_reproj_error": mean_reproj_error}
        pickle.dump(cam_calib_results, open(pkl_file, "wb"))

        return cam_calib_results

    else:
        exit(f"Only one of {basename(output_vid)} or {basename(pkl_file)} exists at {dirname(board_vid)}. \nPlease delete whichever one exists and re-run.") 


def undistort(vid, cam_mtx, dist, framerate):

    """
    TODO: write out these docs 
    """
    vid = expanduser(vid)
    convert_vid_to_jpgs(vid, framerate)
    jpgs_dir = path.join(dirname(vid), basename(splitext(vid)[0])) 
    jpgs = [str(path.absolute()) for path in Path(jpgs_dir).rglob("*.jpg")]

    undistorted_dir = path.join(dirname(vid), f"undistorted_{basename(splitext(vid)[0])}")

    if Path(undistorted_dir).is_dir():

        print(f"{basename(undistorted_dir)} already exists at {dirname(undistorted_dir)}. Skipping ...")

    else:
        
        mkdir(undistorted_dir)
        print(f"Undistorting '{basename(vid)}' ...")
    
        for i, jpg in enumerate(jpgs):

            img = cv2.imread(jpg)
            h, w = img.shape[:2]

            # Tailor the camera matrix: 
            new_cam_mtx, roi = cv2.getOptimalNewCameraMatrix(cam_mtx, dist, (w,h), 1, (w,h))
            
            # Undistort using the original and new cam matrices: 
            undistorted = cv2.undistort(img, cam_mtx, dist, None, new_cam_mtx)

            # Crop the image
            x,y,w,h = roi
            undistorted = undistorted[y:y+h, x:x+w]
            cv2.imwrite(path.join(undistorted_dir, f"undistorted_{i:08d}.jpg"), undistorted) 


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board_vid", 
        help="Path to the input calibration video of the checkerboard")
    parser.add_argument("framerate",
        help="Framerate (int)")
    parser.add_argument("m_corners",
        help="Number of internal corners along the rows of the checkerboard")
    parser.add_argument("n_corners",
        help="Number of internal rows along the corners of the checkerboard")
    parser.add_argument("vid_to_undistort",
        help="Path to the target video for undistortion")
    parser.add_argument("--debug", "-d", action="store_true", 
        help="Show a live feed of the labelled checkerboards, and save a \
            directory of the labelled checkerboards as .jpgs.")
    args = parser.parse_args()

    board_vid = expanduser(args.board_vid)
    framerate = args.framerate
    m_corners = int(args.m_corners)
    n_corners = int(args.n_corners)
    vid_to_undistort = args.vid_to_undistort
    do_debug = args.debug

    cam_calib_results = calibrate_checkerboard(board_vid, m_corners, n_corners, 
                                               framerate=framerate, do_debug=do_debug) 

    cam_mtx, dist = cam_calib_results["cam_mtx"], cam_calib_results["dist"]

    # TODO: use Path().rglob("*.mp4") to undistort multiple vids at once, then update docs: 
    # undistort(vid_to_undistort, cam_mtx, dist, framerate)

            
if __name__ == "__main__":
    main()