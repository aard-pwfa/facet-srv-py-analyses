#!/usr/bin/env python3
from fft import fft
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits import mplot3d as m3d  # NOQA
import E200
import argparse
from classes import *  # NOQA
import ipdb
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import os
import pytools as mt
import pytools.facettools as mtft
import pytools.imageprocess as mtim
import pytools.qt as mtqt
import shlex
import subprocess
import sys
import tempfile


def run_analysis(save=False, check=False, debug=False, verbose=False, movie=False, pdf=False, elog=False, filename=None):
    # ======================================
    # User selects file
    # ======================================
    if filename is None:
        data = E200.E200_load_data_gui()
    else:
        data = E200.E200_load_data(filename)

    loadname  = os.path.splitext(os.path.basename(data.filename))[0]

    # ======================================
    # User decides whether to view view
    # selected regions
    # ======================================
    reply = mtqt.ButtonMsg(title='Show full analysis?', buttons=['Yes', 'No'], maintext='Show individual images analyzed? (MUCH slower)')

    if reply.clickeditem == 'Yes':
        check = True
    elif reply.clickeditem == 'No':
        check = False

    # ======================================
    # Prep save folder
    # ======================================
    savedir = 'output'
    if not os.path.isdir(savedir):
        os.makedirs(savedir)

    # ======================================
    # Prep pdf
    # ======================================
    if pdf or elog:
        if pdf:
            pdffilename = 'output.pdf'
        elif elog:
            tempdir_pdf = tempfile.TemporaryDirectory()
            pdffilename = os.path.join(tempdir_pdf.name, 'output.pdf')
            pngfilename = os.path.join(tempdir_pdf.name, 'out.png')

        pdfpgs = PdfPages(filename=pdffilename)

    # ======================================
    # Load data
    # ======================================
    # savefile = os.path.join(os.getcwd(), 'local.h5')
    # f = h5.File(savefile, 'r', driver='core', backing_store=False)
    # data = E200.Data(read_file = f)
    
    # ======================================
    # Cameras to process
    # ======================================
    camlist      = ['AX_IMG1', 'AX_IMG2']
    radii        = [2, 1]
    calibrations = [10e-6, 17e-6]

    # ======================================
    # UIDs in common
    # ======================================
    uids = np.empty(2, dtype=object)
    for i, cam in enumerate(camlist):
        imgstr  = getattr(data.rdrill.data.raw.images, cam)
        uids[i] = imgstr.UID
    
    uids_wanted = np.intersect1d(uids[0], uids[1])
    uids_wanted = uids_wanted[uids_wanted > 1e5]
    num_uids    = np.size(uids_wanted)
    
    # ======================================
    # Process cameras
    # ======================================
    blobs = np.empty(2, dtype=object)
    for i, (cam, radius, cal) in enumerate(zip(camlist, radii, calibrations)):
        imgstr = getattr(data.rdrill.data.raw.images, cam)
        blob = BlobAnalysis(imgstr, imgname=cam, cal=cal, reconstruct_radius=1, check=check, debug=debug, verbose=verbose, movie=movie, save=save, uids=uids_wanted)

        if save or check or pdf or elog:
            fig = blob.camera_figure(save=save, dataset=loadname)
            if pdf or elog:
                pdfpgs.savefig(fig)
            if check:
                # plt.show()
                plt.draw()
                plt.pause(0.0001)
        blobs[i] = blob

    # ======================================
    # Process centroids into array of coords
    # correlated for 3d plotting
    # ======================================
    z = np.array((0, 1.5))
    coords = np.empty([0, num_uids, 3])
    for i, blob in enumerate(blobs):
        z = i*1.5 * np.ones((np.size(blob.centroid, 0), 1))
        # ipdb.set_trace()
        temp_cent = blob.centroid
        centered = temp_cent - np.mean(temp_cent, axis=0)
        coord = np.append(centered, z, axis=1)
        coords = np.append(coords, [coord], axis=0)

    # ======================================
    # Plot relative 3D trajectories
    # ======================================
    fig = plt.figure(figsize=(16, 6))
    gs = gridspec.GridSpec(1, 2)
    ax1 = fig.add_subplot(gs[0, 0], projection='3d')
    ax2 = fig.add_subplot(gs[0, 1], projection='3d')
    # maxwidth = np.max(blobs[0].sigma_x * blobs[0].sigma_y)
    # widths = blobs[0].sigma_x[i]*blobs[0].sigma_y[i] / maxwidth
    for i, coord in enumerate(coords.swapaxes(0, 1)):
        ax1.plot(coord[:, 2], coord[:, 0]*1e6, coord[:, 1]*1e6)
        ax2.plot(coord[:, 2], coord[:, 0]*1e6, coord[:, 1]*1e6)
    mt.addlabel(ax=ax1, toplabel='Centroid Trajectory', xlabel='z [m]', ylabel='x [$\mu$m]', zlabel='y [$\mu$m]')
    mt.addlabel(ax=ax2, toplabel='Centroid Trajectory', xlabel='z [m]', ylabel='x [$\mu$m]', zlabel='y [$\mu$m]')
    fig.tight_layout()

    if pdf or elog:
        ax1.view_init(elev=45., azim=-60)
        ax2.view_init(elev=0., azim=0)
        mainfigtitle = '3D Plot'
        fig.suptitle(mainfigtitle, fontsize=22)
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        pdfpgs.savefig(fig)

    # ======================================
    # Make a movie
    # ======================================
    if movie:
        with tempfile.TemporaryDirectory() as tempdir:
            for ii in range(0, 360, 1):
                sys.stdout.write('\rFrame: {}'.format(ii))
                ax1.view_init(elev=45., azim=ii-60)
                ax2.view_init(elev=0., azim=ii-60)
                fig.savefig(os.path.join(tempdir, 'movie_{:03d}.tif'.format(ii)))

            fileinput = os.path.join(tempdir, 'movie_%03d.tif')
            command = 'ffmpeg -y -framerate 30 -i {fileinput:} -vcodec h264 -r 30 -pix_fmt yuv420p {savedir:}/out.mov'.format(fileinput=fileinput, savedir=savedir)
            subprocess.call(shlex.split(command))

    # ======================================
    # Calculate angles
    # ======================================
    dx = coords[0, :, 0] - coords[1, :, 0]
    dy = coords[0, :, 1] - coords[1, :, 1]
    ds = np.sqrt(dx**2 + dy**2)
    theta = np.arctan(ds/z.flat)
    theta_urad = theta * 1e6
    # phi = np.arctan2(dy, dx)
    # phi = phi * (phi >= 0) + (phi < 0) *  (-phi + 2*np.pi)

    # ======================================
    # Plot joint analysis
    # ======================================
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(2, 2)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(theta_urad, '-o')
    mt.addlabel(ax=ax1, toplabel='Coordinate: $\\theta$', xlabel='Shot', ylabel='Angle Deviation from Average [$\mu$rad]')

    ax2 = fig.add_subplot(gs[1, 0])
    mt.hist(theta_urad, bins=15, ax=ax2)
    mt.addlabel(ax=ax2, toplabel='Coordinate: $\\theta$', xlabel='Angle Deviation from Average [$\mu$rad]')

    ax3 = fig.add_subplot(gs[0, 1])
    # ax3.plot(phi, '-o')
    n_color = np.size(dx)
    color = np.linspace(1, n_color, n_color)
    ax3_p = ax3.scatter(dx*1e6, dy*1e6, c=color, marker='o', cmap=plt.get_cmap('Greys'))
    cb    = plt.colorbar(ax3_p)
    mt.addlabel(ax=ax3, xlabel='$\Delta x$ ($\mu$m)', ylabel = '$\Delta y$ ($\mu$m)', toplabel='Deviation from Straight-Ahead Average', cb=cb, clabel='Shot Number')

    ax4 = fig.add_subplot(gs[1, 1])
    # mt.hist(phi, bins=15, ax=ax4)
    mt.hist2d(dx*1e6, dy*1e6, cmap=plt.get_cmap('Greys'), ax=ax4, interpolation='nearest')
    mt.addlabel(ax=ax4, xlabel='$\Delta x$ ($\mu$m)', ylabel = '$\Delta y$ ($\mu$m)', toplabel='Deviation from Straight-Ahead Average')

    mainfigtitle = 'Pointing Stability'
    fig.suptitle(mainfigtitle, fontsize=22)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    # ======================================
    # Save joint analysis
    # ======================================
    if save:
        filename = os.path.join(savedir, 'PointingStability.png')
        fig.savefig(filename)

    # ======================================
    # Save pdf
    # ======================================
    if pdf or elog:
        # ======================================
        # Save final fig
        # ======================================
        pdfpgs.savefig(fig)

        freq=data.rdrill.data.raw.metadata.E200_state.EVNT_SYS1_1_BEAMRATE.dat[0]
        fig = fft(blobs, camlist, freq=freq)
        pdfpgs.savefig(fig)

        pdfpgs.close()

        if elog:
            mtim.pdf2png(file_in=pdffilename, file_out=pngfilename)
            author = 'E200 Python'
            title  = 'Laser Stability: {}'.format(loadname)
            text   = 'Laser stability analysis of AX_IMG and AX_IMG2. Comment: {}'.format(E200._numarray2str(data.rdrill.data.raw.metadata.param.comt_str))
            file   = pngfilename
            link   = pdffilename

            mtft.print2elog(author=author, title=title, text=text, link=link, file=file)

        if not pdf:
            # ======================================
            # Clean temp pdf directory
            # ======================================
            tempdir_pdf.cleanup()

    # ======================================
    # Show plots, debug
    # ======================================
    if debug:
        plt.ion()
        plt.show()
        ipdb.set_trace()
    else:
        plt.show()

    return blobs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=
            'Analyzes laser stability.')
    parser.add_argument('-V', action='version', version='%(prog)s v0.1')
    parser.add_argument('-v', '--verbose', action='store_true',
            help='Verbose mode.')
    parser.add_argument('-s', '--save', action='store_true',
            help='Save movie files')
    parser.add_argument('-c', '--check', action='store_true',
            help='View analysis')
    parser.add_argument('-d', '--debug', action='store_true',
            help='Open debugger after running')
    parser.add_argument('-m', '--movie', action='store_true',
            help='Generate movie')
    parser.add_argument('-p', '--pdf', action='store_true',
            help='Generate pdf')
    parser.add_argument('-e', '--elog', action='store_true',
            help='Print to elog')
    parser.add_argument('-f', '--filename',
            help='Dataset filename')
    arg = parser.parse_args()

    run_analysis(save=arg.save, check=arg.check, debug=arg.debug, verbose=arg.verbose, movie=arg.movie, pdf=arg.pdf, elog=arg.elog, filename=arg.filename)
