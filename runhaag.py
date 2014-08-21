import capmin
import coopr.environ
import matplotlib.pyplot as plt
import os
import pandas as pd
import pandashp as pdshp
from coopr.opt.base import SolverFactory
from operator import itemgetter

base_directory = os.path.join('data', 'haag_wgs84')
building_shapefile = os.path.join(base_directory, 'building')
edge_shapefile = os.path.join(base_directory, 'edge')
vertex_shapefile = os.path.join(base_directory, 'vertex')
data_spreadsheet = os.path.join(base_directory, 'data.xlsx')


def setup_solver(optim):
    """Change solver options to custom values."""
    if optim.name == 'gurobi':
        # reference with list of option names
        # http://www.gurobi.com/documentation/5.6/reference-manual/parameters
        optim.set_options("TimeLimit=36000")  # seconds
        optim.set_options("MIPFocus=1")  # 1=feasible, 2=optimal, 3=bound
        optim.set_options("MIPGap=1e-4")  # default = 1e-4
        optim.set_options("Threads=6")  # number of simultaneous CPU threads
    elif optim.name == 'glpk':
        # reference with list of options
        # execute 'glpsol --help'
        pass
    else:
        print("Warning from setup_solver: no options set for solver "
            "'{}'!".format(optim.name))
    return optim

# load buildings and sum by type and nearest edge ID
# 1. read shapefile to DataFrame (with special geometry column)
# 2. group DataFrame by columns 'nearest' (ID of nearest edge) and 'type'
#    (residential, commercial, industrial, other)
# 3. sum by group and unstack, i.e. convert secondary index 'type' to columns
buildings = pdshp.read_shp(building_shapefile)
building_type_mapping = { 
'church': 'other', 
'farm': 'other',
'hospital': 'residential',  
'hotel': 'commercial',
'house': 'residential',
'office': 'commercial',
'retail': 'commercial', 
'school': 'commercial',  
'yes': 'other',
}
buildings.replace(to_replace={'type': building_type_mapping}, inplace=True)
buildings_grouped = buildings.groupby(['nearest', 'type'])
total_area = buildings_grouped.sum()['AREA'].unstack()

# load edges (streets) and join with summed areas 
# 1. read shapefile to DataFrame (with geometry column)
# 2. join DataFrame total_area on index (=ID)
# 3. fill missing values with 0
edge = pdshp.read_shp(edge_shapefile)
edge = edge.set_index('Edge')
edge = edge.join(total_area)
edge = edge.fillna(0)

# load nodes
vertex = pdshp.read_shp(vertex_shapefile)

# load spreadsheet data
data = capmin.read_excel(data_spreadsheet)

# create & solve model
model = capmin.create_model(data, vertex, edge)
prob = model.create()
optim = SolverFactory('gurobi')
optim = setup_solver(optim)
result = optim.solve(prob, tee=True)
prob.load(result)

# prepare input data similar to model for easier analysis
entity_getter = itemgetter(
    'commodity', 'process', 'process_commodity', 'time', 'area_demand')
commodity, process, process_commodity, time, area_demand = entity_getter(data)


costs, Pmax, Kappa_hub, Kappa_process = capmin.get_constants(prob)
source, flows, hub_io, proc_io, proc_tau = capmin.get_timeseries(prob)

# plot all caps (and demands if existing)
for com, plot_type in [('Elec', 'caps'), ('Heat', 'caps'), ('Gas', 'caps'),
                       ('Elec', 'peak'), ('Heat', 'peak')]:
    
    # create plot
    fig = capmin.plot(prob, com, 
                      mapscale=(com=='Elec'), 
                      plot_demand=(plot_type == 'peak'))

    # save to file
    for ext in ['png', 'pdf']:
        result_dir = ps.path.join('result', os.path.basename(base_directory))
        
        # create result directory if not existing already
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
            
        # determine figure filename from plot type, commodity and extension
        fig_filename = os.path.join(
            result_dir, '{}-{}.{}').format(plot_type, com, ext)
        fig.savefig(fig_filename, dpi=300, bbox_inches='tight', 
                    transparent=(ext=='pdf'))
