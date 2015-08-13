#--------------------------------
# Name:         clip_cdl_raster.py
# Purpose:      Clip CDL rasters in order to build agland rasters
# Author:       Charles Morton
# Created       2015-08-12
# Python:       2.7
#--------------------------------

import argparse
import datetime as dt
import logging
import os
import subprocess
import sys

from osgeo import gdal, ogr, osr

import gdal_common as gdc

def main(gis_ws, extent_path, extent_buffer=None,
         overwrite_flag=False, pyramids_flag=False, stats_flag=False):
    """Clip CDL rasters to a target extent and rebuild color table

    Args:
        gis_ws (str): Folder/workspace path of the GIS data for the project
        extent_path (str): file path to study area shapefile
        extent_buffer (float): distance to buffer input extent
            Units will be the same as the extent spatial reference
        overwrite_flag (bool): If True, overwrite output rasters
        pyramids_flag (bool): If True, build pyramids/overviews
            for the output rasters 
    Returns:
        None
    """
    input_cdl_path = r'Z:\USBR_Ag_Demands_Project\CAT_Basins\common\gis\cdl\2010_30m_cdls.img'
    ##input_cdl_path = r'D:\Projects\NLDAS_Demands\common\gis\cdl\2013_30m_cdls.img'
    ##input_cdl_path = r'N:\Texas\ETDemands\common\gis\cdl\2013_30m_cdls.img'

    cdl_year = 2010
    cdl_ws = os.path.join(gis_ws, 'cdl')
    clip_path = os.path.join(cdl_ws, '{}_30m_cdls.img'.format(cdl_year))

    ## Reference all output rasters to CDL
    output_osr = gdc.raster_path_osr(input_cdl_path)
    output_cs = gdc.raster_path_cellsize(input_cdl_path)[0]
    output_x, output_y = gdc.raster_path_origin(input_cdl_path)
    ##output_osr = gdc.proj4_osr(
    ##    "+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23 +lon_0=-96 +x_0=0 +y_0=0 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs")
    ##output_cs = 30
    ##output_x, output_y = 15, 15

    if pyramids_flag:
        levels = '2 4 8 16 32 64 128'

    ## Check input folders
    if not os.path.isdir(gis_ws):
        logging.error('\nERROR: The GIS workspace {} '+
                      'does not exist'.format(gis_ws))
        sys.exit()
    elif not os.path.isfile(input_cdl_path):
        logging.error(
            ('\nERROR: The input CDL raster {} '+
             'does not exist').format(input_cdl_path))
        sys.exit()
    elif not os.path.isfile(extent_path):
        logging.error(
            ('\nERROR: The extent shapefile {} '+
             'does not exist').format(extent_path))
        sys.exit()
    if not os.path.isdir(cdl_ws):
        os.makedirs(cdl_ws)
    logging.info('\nGIS Workspace:  {}'.format(gis_ws))
    logging.info('CDL Workspace:  {}'.format(cdl_ws))

    ## Overwrite
    if os.path.isfile(clip_path) or overwrite_flag:
        subprocess.call(['gdalmanage', 'delete', clip_path])
        ##remove_file(clip_path)

    ## Clip
    if not os.path.isfile(clip_path):
        ## Get the study area extent from a shapefile
        clip_osr = gdc.feature_path_osr(extent_path)
        logging.debug('Clip OSR: {}'.format(clip_osr))
        clip_extent = gdc.path_extent(extent_path)
        logging.debug('Clip Extent: {}'.format(clip_extent))
        if extent_buffer is not None:
            logging.debug('Buffering: {}'.format(extent_buffer))
            clip_extent.buffer_extent(extent_buffer)
            logging.debug('Clip Extent: {}'.format(clip_extent))
            
        ## Project study area extent to the output/CDL spatial reference
        clip_extent = gdc.project_extent(clip_extent, clip_osr, output_osr)
        clip_extent.adjust_to_snap('EXPAND', output_x, output_y, output_cs)
        logging.debug('Clip Extent: {0}'.format(clip_extent))

        ##gdal_translate uses ul/lr corners, not extent
        clip_ullr = clip_extent.ul_lr_swap()
        logging.debug('Clip UL/LR:  {0}'.format(clip_ullr))
        
        subprocess.call(
            ['gdal_translate', '-of', 'HFA']+
            ['-projwin'] + str(clip_ullr).split() +
            ['-a_ullr'] + str(clip_ullr).split() + 
            [input_cdl_path, clip_path])
        ##subprocess.call(
        ##    ['gdalwarp', '-overwrite', '-of', 'HFA']+
        ##    ['-te'] + str(clip_extent).split() +
        ##    ['-tr', '{0}'.format(input_cs), '{0}'.format(input_cs),
        ##    [input_cdl_path, clip_path])

        ## Get class names from CDL raster
        logging.info('Read RAT')
        input_ds = gdal.Open(input_cdl_path, 0)
        input_band = input_ds.GetRasterBand(1)
        input_rat = input_band.GetDefaultRAT()
        classname_dict = dict()
        for row_i in range(input_rat.GetRowCount()):
            classname_dict[row_i] = input_rat.GetValueAsString(
                row_i, input_rat.GetColOfUsage(2))
        input_ds = None
        del input_ds, input_band, input_rat

        ## Set class names in the clipped CDL raster
        logging.info('Write RAT',)
        clip_ds = gdal.Open(clip_path, 1)
        clip_band = clip_ds.GetRasterBand(1)
        clip_rat = clip_band.GetDefaultRAT()
        clip_usage_list = [
            clip_rat.GetUsageOfCol(col_i)
            for col_i in range(clip_rat.GetColumnCount())]
        logging.debug(clip_usage_list)
        ##if 1 not in clip_usage_list:
        ##    clip_rat.CreateColumn('Count', 1, 1)
        if 2 not in clip_usage_list:
            clip_rat.CreateColumn('Class_Name', 2, 2)
        for row_i in range(clip_rat.GetRowCount()):
            clip_rat.SetValueAsString(
                row_i, clip_rat.GetColOfUsage(2), classname_dict[row_i])
        clip_band.SetDefaultRAT(clip_rat)
        ## Check that they were written to the RAT
        ##clip_rat = clip_band.GetDefaultRAT()
        ##for row_i in range(clip_rat.GetRowCount()):
        ##    print clip_rat.GetValueAsString(row_i, clip_rat.GetColOfUsage(2))
        clip_ds = None

    ## Statistics
    if stats_flag and os.path.isfile(clip_path):
        logging.info('Computing statistics')
        logging.debug('  {0}'.format(clip_path))
        subprocess.call(['gdalinfo', '-stats', '-nomd', clip_path])

    ## Pyramids
    if pyramids_flag and os.path.isfile(clip_path):
        logging.info('Building statistics')
        logging.debug('  {0}'.format(clip_path))
        subprocess.call(['gdaladdo', '-ro', clip_path] + levels.split())

################################################################################

def arg_parse():
    parser = argparse.ArgumentParser(
        description='Clip CDL Rasters',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--gis', nargs='?', default=os.getcwd(), metavar='FOLDER',
        help='GIS workspace/folder')
    parser.add_argument(
        '--extent', required=True, metavar='FILE',
        help='Study area shapefile')
    parser.add_argument(
        '--buffer', default=None, metavar='FLOAT', type=float,
        help='Extent buffer')
    parser.add_argument(
        '--overwrite', default=None, action='store_true',
        help='Overwrite existing files')
    parser.add_argument(
        '--pyramids', default=None, action='store_true',
        help='Build pyramids')
    parser.add_argument(
        '--stats', default=None, action='store_true',
        help='Build statistics')
    parser.add_argument(
        '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action="store_const", dest="loglevel")
    args = parser.parse_args()

    ## Convert input file to an absolute path
    if args.gis and os.path.isdir(os.path.abspath(args.gis)):
        args.gis = os.path.abspath(args.gis)
    if args.extent and os.path.isfile(os.path.abspath(args.extent)):
        args.extent = os.path.abspath(args.extent)
    return args

################################################################################
if __name__ == '__main__':
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')  
    logging.info('\n%s' % ('#'*80))
    logging.info('%-20s %s' % ('Run Time Stamp:', dt.datetime.now().isoformat(' ')))
    logging.info('%-20s %s' % ('Current Directory:', os.getcwd()))
    logging.info('%-20s %s' % ('Script:', os.path.basename(sys.argv[0])))

    main(gis_ws=args.gis, extent_path=args.extent, extent_buffer=args.buffer, 
         overwrite_flag=args.overwrite, pyramids_flag=args.pyramids,
         stats_flag=args.stats)