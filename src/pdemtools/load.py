"""
This module contains the functions necessary to open the ArcticDEM/REMA strip as an 
xarray DataArray, from either local or AWS sources. 
"""

import os
from typing import Optional, Literal, Union
from importlib import resources

import rioxarray as rxr
import geopandas as gpd

from rioxarray.merge import merge_arrays
from xarray import DataArray
from shapely.geometry.polygon import Polygon
from geopandas.geodataframe import GeoDataFrame

from ._utils import clip

# arctic and rema valid versions for STAC retrival
VERSIONS = {"arcticdem": ["v3.0", "v4.1"], "rema": ["v2.0"]}

# filenames of mosaic indexes in ./src/pdemtools/mosaic_index directory
ARCTICDEM_V3_INDEX_FNAME = "ArcticDEM_Mosaic_Index_v3_gpkg.gpkg"
ARCTICDEM_V3_INDEX_2M_LAYER_NAME = "ArcticDEM_Mosaic_Index_v3_2m"
ARCTICDEM_V4_INDEX_FNAME = "ArcticDEM_Mosaic_Index_v4_1_gpkg.gpkg"
ARCTICDEM_V4_INDEX_2M_LAYER_NAME = "ArcticDEM_Mosaic_Index_v4_1_2m"
REMA_V2_INDEX_FNAME = "REMA_Mosaic_Index_v2_gpkg.gpkg"
REMA_V2_INDEX_2M_LAYER_NAME = "REMA_Mosaic_Index_v2_2m"

# aws location
PREFIX = "https://pgc-opendata-dems.s3.us-west-2.amazonaws.com"

# valid mosaic resolutions
VALID_MOSAIC_RES = ["2m", "10m", "32m"]


def from_fpath(
    dem_fpath: str,
    bounds: Optional[Union[tuple, Polygon]] = None,
    bitmask_fpath: Optional[str] = None,
) -> DataArray:
    """Given a filepath (local or an AWS link) the desired ArcticDEM/REMA DEM strip as
    an xarray DataArray. Option to filter to bounds and bitmask, if provided.

    :param dem_fpath: Filepath of DEM strip
    :type dem_fpath: str
    :param bounds: Clip to bounds [xmin, ymin, xmax, ymax], in EPSG:3413 (ArcticDEM) or
        EPSG:3031 (REMA). Will accept a shapely geometry to extract bounds from.
        Defaults to None
    :type bounds: tuple | Polygon, optional
    :param mask_fpath: Path to *_bitmask.tif file used to mask the DEM, defaults to None
    :type mask_fpath: str, optional

    :returns: xarray DataArray of DEM strip
    :rtype: DataArray
    """

    # Open dataarray using rioxarray
    dem = rxr.open_rasterio(dem_fpath)

    # Convert shapely geometry to bounds
    if type(bounds) == Polygon:
        bounds = bounds.bounds

    # Clip if requested, or get whole bounds if not
    if bounds is not None:
        dem = clip(dem, bounds)
    else:
        bounds = dem.rio.bounds()

    # Filter -9999.0 values
    dem = dem.where(dem > -9999.0)

    # Mask using bitmask if requested
    if bitmask_fpath is not None:
        mask = rxr.open_rasterio(bitmask_fpath)
        if bounds is not None:
            mask = clip(mask, bounds)
        dem = dem.where(mask == 0)
        del mask

    # Remove `band` dim
    dem = dem.squeeze(drop=True)

    return dem


def preview(
    row: GeoDataFrame,
    bounds: Optional[Union[tuple, Polygon]] = None,
):
    """Loads a 10 m hillshade preview of the desired ArcticDEM/REMA DEM strip as an xarray
    DataArray, for preliminary plotting and assessment. Option to filter to bounds.

    :param row: A selected row from the GeoDataFrame output of pdemtools.search. Can
        either select a row manually using gdf.isel[[i]] where `i` is the desired row,
        or provide the entire GeoDataFrame,
    :type row: GeoDataFrame
    :param bounds: Clip to bounds [xmin, ymin, xmax, ymax], in EPSG:3413 (ArcticDEM) or
        EPSG:3031 (REMA). Will accept a shapely geometry to extract bounds from.
        Defaults to None
    :type bounds: tuple | Polygon, optional

    :returns: xarray DataArray of DEM strip 10 m hillshade
    :rtype: DataArray
    """

    try:
        s3url = row.s3url.values[0]
    except:
        s3url = row.s3url

    json_url = "http://" + s3url.split("/external/")[1]
    hillshade_10m_url = json_url.replace(".json", "_dem_10m_shade_masked.tif")

    preview = from_fpath(hillshade_10m_url, bounds)
    return preview.where(preview > 0)


def from_search(
    row: GeoDataFrame,
    bounds: Optional[Union[tuple, Polygon]] = None,
    bitmask: bool = True,
):
    """Loads the 2 m DEM strip of the  desired ArcticDEM/REMA DEM strip as an xarray
    DataArray. Option to filter to bounds, if provided, and bitmask, if set to True
    (default True).

    :param row: A selected row from the GeoDataFrame output of pdemtools.search. Can
        either select a row manually using gdf.isel[[i]] where `i` is the desired row,
        or provide the entire GeoDataFrame,
    :type row: GeoDataFrame
    :param bounds: Clip to bounds [xmin, ymin, xmax, ymax], in EPSG:3413 (ArcticDEM) or
        EPSG:3031 (REMA). Will accept a shapely geometry to extract bounds from.
        Defaults to None
    :type bounds: tuple | Polygon, optional
    :param bitmask: Choose whether apply the associated bitmask, defaults to True
    :type bitmask: bool, optional

    :returns: xarray DataArray of DEM strip
    :rtype: DataArray
    """

    try:
        s3url = row.s3url.values[0]
    except:
        s3url = row.s3url

    json_url = "http://" + s3url.split("/external/")[1]
    dem_url = json_url.replace(".json", "_dem.tif")

    # Construct bitmask fpath, if required
    if bitmask == True:
        bitmask_url = json_url.replace(".json", "_bitmask.tif")
    else:
        bitmask_url = None

    # Pass AWS URL locations to load_local command
    return from_fpath(
        dem_url,
        bounds,
        bitmask_url,
    )


def from_id(
    dataset: Literal["arcticdem", "rema"],
    geocell: str,
    dem_id: str,
    bounds: Optional[Union[tuple, Polygon]] = None,
    bitmask: Optional[bool] = True,
    bucket: Optional[str] = "https://pgc-opendata-dems.s3.us-west-2.amazonaws.com",
    version: Optional[str] = "s2s041",
    preview: Optional[bool] = False,
) -> DataArray:
    """An alternative method of loading the selected ArcticDEM/REMA strip, which
    requires only the geocell and the dem_id (e.g. geocell = 'n70w051', dem_id =
    'SETSM_s2s041_WV01_20200709_102001009A689B00_102001009B63B200_2m_lsf_seg2').
    Downloads from the relevant AWS bucket, as an xarray DataArray. Option to filter to
    bounds and bitmask. 2 m DEM strips are large in size and loading remotely from AWS
    may take some time.

    :param dataset: Either 'arcticdem' or 'rema'. Case-insensitive.
    :type dataset: str
    :param geocell: Geographic grouping of ArcticDEM / REMA strip. e.g. 'n70w051'.
    :type geocell: str
    :param dem_id: ArcticDEM/REMA strip ID. e.g.
        'SETSM_s2s041_WV01_20200709_102001009A689B00_102001009B63B200_2m_lsf_seg2'
    :type dem_id: str
    :param bounds: Clip to bounds [xmin, ymin, xmax, ymax], in EPSG:3413 (ArcticDEM) or
        EPSG:3031 (REMA), defaults to None
    :type bounds: tuple, optional
    :param bitmask: Choose whether apply the associated bitmask, defaults to True
    :type bitmask: bool, optional
    :param bucket: AWS buck link, defaults to
        'https://pgc-opendata-dems.s3.us-west-2.amazonaws.com'
    :type bucket: str
    :param version: Version string, defaults to 's2s041'
    :type version: str
    :param preview: Return just a link to the STAC preview page, defaults to False
    :type preview: bool, optional

    :return: xarray DataArray of DEM strip
    :retype: DataArray
    """

    # Sanitise data
    dataset = dataset.lower()
    geocell = geocell.lower()

    if preview == True:
        browser_prefix = "https://polargeospatialcenter.github.io/stac-browser/#/external/pgc-opendata-dems.s3.us-west-2.amazonaws.com"
        preview_fpath = os.path.join(
            browser_prefix, dataset, "strips", version, "2m", geocell, f"{dem_id}.json"
        )
        return preview_fpath

    # Construct DEM fpath
    dem_fpath = os.path.join(
        bucket, dataset, "strips", version, "2m", geocell, f"{dem_id}_dem.tif"
    )

    # Construct bitmask fpath, if required
    if bitmask == True:
        bitmask_fpath = os.path.join(
            bucket, dataset, "strips", version, "2m", geocell, f"{dem_id}_bitmask.tif"
        )
    else:
        bitmask_fpath = None

    # Pass AWS URL locations to load_local command
    return from_fpath(
        dem_fpath,
        bounds,
        bitmask_fpath,
    )


def mosaic(
    dataset: Literal["arcticdem", "rema"],
    resolution: Literal["2m", "10m", "32m"],
    bounds: Union[tuple, Polygon] = None,
    version: Optional[Literal["v2.0", "v3.0", "v4.1"]] = None,
):
    """Given a dataset, resolution, and bounding box, download the ArcticDEM or REMA
    mosiac.

    :param dataset: The desired dataset, either 'arcticdem' or 'rema'.
        Case-instensitive.
    :type datasat: str
    :param resolution: The desired mosaic resolution to download - must be either '2m',
        '10m', or '32m' (will also accept 2, 10, and 32 as `int` types)
    :type resolutions: str | int
    :param version: Desired ArcticDEM or REMA version. Must be a valid version available
        from the PGC STAC API (e.g. `v3.0` or `v4.1` for ArcticDEM, or `v2.0` for REMA).
    :type version: str
    :param bounds: Clip to bounds [xmin, ymin, xmax, ymax], in EPSG:3413 (ArcticDEM) or
        EPSG:3031 (REMA). Will accept a shapely geometry to extract bounds from.
    :type bounds: tuple | Polygon, optional
    """

    # sanity check that datset and versioning is correct versioning is valid for selected dataset
    dataset = dataset.lower()
    if dataset not in VERSIONS.keys():
        raise ValueError(
            f"Dataset must be one of {VERSIONS.keys}. Currently `{dataset}`."
        )
    if version == None:  # pick the most recent dataset
        version = VERSIONS[dataset][-1]
    else:
        if version not in VERSIONS[dataset]:
            raise ValueError(
                f"Version of {dataset} must be one of {VERSIONS[dataset]}. Currently `{version}`"
            )

    # get resolution as str
    if type(resolution) == int:
        resolution = f"{resolution}m"

    # check if valid resolution
    if resolution not in VALID_MOSAIC_RES:
        raise ValueError(
            f"Resolution must be one of {VALID_MOSAIC_RES}. Currently `{resolution}`"
        )

    # Sanitise shapely geometry to bounds tuple
    if type(bounds) == Polygon:
        bounds = bounds.bounds

    # get dataset version
    if dataset == "arcticdem" and version == "v3.0":
        layer = ARCTICDEM_V3_INDEX_2M_LAYER_NAME
    elif dataset == "arcticdem" and version == "v4.1":
        layer = ARCTICDEM_V4_INDEX_2M_LAYER_NAME
    elif dataset == "rema" and version == "v2.0":
        layer = REMA_V2_INDEX_2M_LAYER_NAME
    else:
        raise ValueError(
            "Cannot retrive internal index filepath for specified dataset and version."
        )

    # Load tiles that intersect with AOI
    tiles = gpd.read_file(
        _get_index_fpath(dataset, version=version), layer=layer, bbox=bounds
    )

    if len(tiles) < 1:
        raise ValueError(
            "No {dataset} mosaic tiles found to intersect with bounds {aoi}"
        )

    # get aws filepaths from the tiles dataframe
    fpaths = []
    for _, row in tiles.iterrows():
        fpath = _aws_link(row, dataset=dataset, version=version, resolution=resolution)
        fpaths.append(fpath)

    # remove duplicates in 10m and 32m (which load supertiles, not tiles)
    fpaths = list(set(fpaths))

    # load dem(s)
    dems = []
    for fpath in fpaths:
        dem = rxr.open_rasterio(fpath).rio.clip_box(*bounds)
        dems.append(dem)

    if len(fpaths) == 1:
        dem = rxr.open_rasterio(fpaths[0]).rio.clip_box(*bounds)

    # If multiple dems, merge them
    if len(dems) > 1:
        dem = merge_arrays(dems)
    else:
        dem = dems[0]

    # Filter -9999.0 values to np.nan
    dem = dem.where(dem > -9999.0)

    return dem


def _get_index_fpath(
    dataset: Literal["arcticdem", "rema"],
    version: Literal["v2.0", "v3.0", "v4.0"],
):
    """Given `arcticdem` or `rema`, gets the filepath of the package dataset using the
    `importlib` library. ARCTICDEM and REMA global variables necessary.
    """

    # get dataset version
    if dataset == "arcticdem" and version == "v3.0":
        fname = ARCTICDEM_V3_INDEX_FNAME
    elif dataset == "arcticdem" and version == "v4.1":
        fname = ARCTICDEM_V4_INDEX_FNAME
    elif dataset == "rema" and version == "v2.0":
        fname = REMA_V2_INDEX_FNAME
    else:
        raise ValueError(
            "Cannot retrive internal index filepath for specified dataset and version."
        )

    return resources.files("pdemtools.mosaic_index").joinpath(fname)


def _aws_link(
    row,
    dataset: Literal["arcticdem", "rema"],
    version: str,
    resolution: Literal["2m", "10m", "32m"],
    prefix: Optional[str] = PREFIX,
):
    """Using inputs from mosaic() function and the AWS location from the global variable
    `PREFIX`, construct the filepath of the relevant ArcticDEM or REMA mosaic tile.
    """
    # Construct appropriate suffix, considering ArcticDEM v3.0's alternate naming scheme
    if dataset == "arcticdem" and version == "v3.0":
        suffix = f"_{resolution}_{version}_reg_dem.tif"
    else:
        suffix = f"_{resolution}_{version}_dem.tif"

    # Construct appropriate filename given resolution
    if resolution == "2m":
        fname = f"{row.tile}{suffix}"
    elif resolution in ["10m", "32m"]:
        fname = f"{row.supertile}{suffix}"
    else:
        raise ValueError(f"Input `resolution` must be one of ['2m', '10m', '32m']")

    # Return appropriate filepath.
    return os.path.join(
        prefix, dataset, "mosaics", version, resolution, row.supertile, fname
    )
