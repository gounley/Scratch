#!/usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
"""
Created on Thu Sep  7 11:10:38 2017

@author: johnbauer
"""

# =============================================================================
# Assumes mlskMBO is located in Scratch/mlskMBO, at the same level as Benchmarks
# GitHub
#    Scratch
#        mlskMBO
#    Benchmarks
#        common
#        Pilot1
#            common
#            NT3
# =============================================================================

import os
import sys


def add_path(*args):
    """utility function for joining paths"""
    lib_path = os.path.abspath(os.path.join(*args))
    sys.path.append(lib_path)
    
file_path = os.path.dirname(os.path.realpath(__file__))

# edit this list of paths if needed to match directory locations
paths =  [['..', '..', 'Benchmarks', 'common'],
          ['..', '..', 'Benchmarks', 'Pilot1', 'common'],
          [ '..', '..', 'Benchmarks', 'Pilot1', 'NT3']]

for path in paths:
    p = [file_path]
    p.extend(path)
    add_path(*p)


import run_data as rd
import nt3_baseline_keras2 as nt3b

import parameter_set as prs
import CategoricalKernel as ck
#import CategoricalKernel_cython as ck


import pandas as pd
from collections import defaultdict
import logging

from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import ParameterGrid, ParameterSampler

import scipy as sp
from scipy.stats.distributions import expon
from math import pi

# =============================================================================
# data are correctly reshaped but warning is present any, so suppress them all
# =============================================================================
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning) 



# =============================================================================
# CONFIGURATION stuff done here for now
# =============================================================================
logging.basicConfig(filename='NT3.log',level=logging.DEBUG)
logging.debug("Start NT3")

# if True, parameter dictionaries will be sent to nt3_baseline_keras2
run_keras = False

config_file = os.path.join(file_path, 'nt3_default_model.txt')

# location where keras log will be written
# will be written into parameter dictionary
output_dir = os.path.join(file_path, 'save') 
output_subdirectory = 'experiment_gpr_1' 

# read in global default parametere configuration
default_params = nt3b.read_config_file(config_file)

# don't fit models with ridiculously large losses, as defined here
# there is at least one keras run with a validation loss > 8 
MAX_LOSS = 2

# the target is validation_loss, could be training_loss or runtime_hours
TARGET = 'validation_loss'

# =============================================================================
# ParameterSet generated initial sample grid used to train model
# creates candidate parameter dictionaries after model is trained
# see parameter_set for a more complete parameter set matching R
# =============================================================================
batch_size = [16, 32, 64, 128, 256, 512]
#activation = ["softmax", "elu", "softplus", "softsign", "relu", "tanh", "sigmoid", "hard_sigmoid", "linear"]
dense = [[500, 100, 50],
         [1000, 500, 100, 50],
         [2000, 1000, 500, 100, 50],
         [2000, 1000, 1000, 500, 100, 50],
         [2000, 1000, 1000, 1000, 500, 100, 50]]
#optimizer = ["adam", "sgd", "rmsprop", "adagrad", "adadelta","adamax","nadam"]
conv = [ [50, 50, 50, 50, 50, 1],
         [25, 25, 25, 25, 25, 1],
         [64, 32, 16, 32, 64, 1],
         [100, 100, 100, 100, 100, 1],
         [32, 20, 16, 32, 10, 1]]

ps = prs.ParameterSet()

ps.add(prs.DiscreteParameter("batch_size", batch_size))
ps.add(prs.IntegerParameter("epochs", 5, 100))
#ps.add(prs.DiscreteParameter("activation", activation))
ps.add(prs.DiscreteParameter("dense", dense))
#ps.add(prs.DiscreteParameter("optimizer", optimizer))
ps.add(prs.NumericParameter("drop", 0.0, 0.9))
ps.add(prs.NumericParameter("learning_rate", 0.00001, 0.1))
ps.add(prs.DiscreteParameter("conv", conv))
# TODO: since dense and conv will be dummy-coded, ensure that all possible
# category values are present in the parameter set

# =============================================================================
# DATA
# =============================================================================

# TODO: relocate pdtypes to nt3_run_data
# coerce data into correct types in dataframe
float64 = 'float64'
int64 =  'int64'
pdtypes = {'batch_size': int64,
           'drop': float64,
           'epochs': int64,
           'learning_rate': float64,
           'run_id': int64,
           'runtime_hours' : float64,
           'training_loss' : float64,
           'validation_loss' : float64
           }

# utility function gets data from earlier runs, saved from dataframe to .csv
# or from a directory populated with run._.json log files
def get_nt3_data(output_dir=output_dir,
             subdirectory=output_subdirectory,
             dtype=pdtypes,
             from_csv=False):
    """Assumes json log files from a previous run are available

    If json logs are in output_subdirectory, call with from_csv=False
    Otherwise it will read cached data from a previous run from a .csv file
    """

    if from_csv:
        data = pd.read_csv("nt3_initial_data.csv", dtype=dtype)
    else:
        nt3_data = rd.NT3RunData(output_dir=output_dir,
                                   subdirectory=output_subdirectory)
        nt3_data.add_all()
        data = nt3_data.dataframe
    
    data = data[data.validation_loss < MAX_LOSS]
    return data

data = get_nt3_data(from_csv=True)

#print(data.columns)

# columns to use as predictors in the model
# non-numeric columns will be recoded as as indicator variables for GPR
X_col = ['batch_size', 'conv', 'dense', 'drop', 'epochs', 'learning_rate']
# columns omitted from X: ['run_id', 'runtime_hours', 'training_loss']
assert all(x in data.columns for x in X_col), "invalid column"

# preliminary input for modelling
X = data[X_col]
y = data[TARGET]

# =============================================================================
# Some useful statistics, will be logged eventually
# =============================================================================
yidxmin = y.idxmin()

y_star = y.iloc[yidxmin]
X_star = X.iloc[yidxmin]

print("Best observed value in training data")
print("Index: {}".format(yidxmin))
print(y_star)
print("Parameter values for best observed:")
print(X_star)

# =============================================================================
# Gaussian Process Regresssion Model
# =============================================================================

# =============================================================================
# Create auxiliary dataframe with dummy-coded indicators for dense, conv...
# =============================================================================

# TODO: rework DataFrameWithDummies to implement fit, transform
#data_with_dummies = prs.DataFrameWithDummies(X, dummies=['conv', 'dense'])
factors = ['dense', 'conv']

Xd = pd.get_dummies(data=X, columns=factors, prefix_sep='|')

# find the column numbers corresponding to each factor
continuous_columns = []
factor_columns = defaultdict(list)

for i, name in enumerate(Xd.columns):
    n0 = name.split("|")[0]
    if n0 in factors:
        factor_columns[n0].append(i)
    else:
        continuous_columns.append(i)


n_continuous = len(continuous_columns)

# fairly generic Radial Basis Function kernel with scaling
# fairly broad bounds on the hyperparameters (which are fit automatically) 
#k = ConstantKernel(1.0, (0.001, 1000.0))
kernel = ck.ProjectionKernel(RBF([1.0]*n_continuous, (0.001, 1000.0)), continuous_columns, name="continuous")

factor_kernel = {}
for factor, columns in factor_columns.iteritems():
    dim = len(columns)
    fk = ck.FactorKernel(dim, [2*pi+pi/4.]*(dim*(dim-1)/2))
    factor_kernel[factor] = fk
    kernel *= ck.ProjectionKernel(fk, columns, name=factor)
# =============================================================================
# kernel = ck.ProjectionKernel(RBF([1.0]*n_continuous, (0.001, 1000.0)), continuous_columns, name="continuous")
# for factor, columns in factor_columns.iteritems():
#     dim = len(columns)
#     kernel *= ck.ProjectionKernel(ck.SimpleCategoricalKernel(dim), columns, name=factor)
# =============================================================================

# TODO: figure out if this is worth it, need to project on each coord?
# use standard scaler for now
#k += ConstantKernel([1.0]*n_continuous, [(0.0001, 10000.0)]*n_continuous)

gpr = GaussianProcessRegressor(kernel=kernel, alpha=0.001, n_restarts_optimizer=20, normalize_y=True)
#gpr = GaussianProcessRegressor(kernel=k, alpha=0.001, normalize_y=True)

gpr.fit(Xd, y)

# report the hyperparameters as fit by the model
print(gpr.kernel_.get_params())
for factor, k in factor_kernel.items():
    print("Correlations ({})\n{}".format(factor, k.correlation))

gprpred = pd.DataFrame({"pred" : gpr.predict(Xd)})
print("GPR predictions")
print(gprpred.describe())
gpidx = gprpred.idxmin()
y_gstar = y.iloc[gpidx]
print("observed value corresponding to best prediction")
print(y_gstar)
X_gstar = X.iloc[gpidx]
print("Parameter values for best prediction")
print(X_gstar)
gprpred.plot(title="GPR predictions")

# utility function to override default values
def param_update(params, default_params, run_id, output_subdirectory='exp'):
    run_params = default_params.copy()
    run_params.update(params)
    run_params['save'] = 'save/{}'.format(output_subdirectory)
    #run_params['solr_root'] = "http://localhost:8983/solr"
    run_params['run_id'] = "run.{}.json".format(run_id)
    # TODO: find a better workaround
    # batch_size is a DiscreteParameter but not dummy-coded
    # does not know to validate as integer
    run_params['batch_size'] = int(run_params.get('batch_size', 16))
    return run_params

# =============================================================================
# OPTIMIZATION
# =============================================================================
# n.b. bounds must be supplied in the standardized coordinates
# GPR will not extrapolate to points outside the bounds in the training data
lower_bound = Xd.min(axis=0)
upper_bound = Xd.max(axis=0)

bounds = [(lower, upper) for lower, upper in zip(lower_bound, upper_bound)]
#bounds = gpr.kernel.bounds

# using location of best actual value (yidxmin) as starting point
# other starting points potentailly could find local minima
# minimal testing for NT3 suggests it usually finds the global minimum
start_val = Xd.iloc[yidxmin].as_matrix().reshape(-1,  1)
result = sp.optimize.minimize(gpr.predict, start_val, method='L-BFGS-B', bounds=bounds)

# restore the original coordinates
rx = result.x

# undo the dummy coding
columns = Xd.columns
d = {col : val for col, val in zip(columns, rx)}
d = ps.decode_dummies(d)

# =============================================================================
# Begin amassing a bunch of candidates, starting with the GPR recommendation
# =============================================================================
# len(run_params) generates a unique sequential id number to be used as run_id
# params['save'] will be set to 'save/output_subdirectory'
# resulting log file will be saved as "run.{}.json".format(run_id)
run_params = []
params = param_update(d, default_params, len(run_params), output_subdirectory)
print("Parameters from GPR | optimize")
print(params)
run_params.append(params)

# =============================================================================
# Construct new parameter sets focussed at various degrees on the best so far
# =============================================================================
# more draws at higher levels will explore more broadly
# more layers will narrow the focus more tightly around the initial point
# =============================================================================
INITIAL_GUESSES = 3
FOCUSSED_GUESSES = 3
FOCUS_2_GUESSES = 3

for i in range(INITIAL_GUESSES):
    focus = ps.focus(d)
    for j in range(FOCUSSED_GUESSES):
        params = param_update(focus.draw(), default_params, len(run_params), output_subdirectory)
        run_params.append(params)
        focus2 = ps.focus(d)
        for k in range(FOCUS_2_GUESSES):
            params = param_update(focus2.draw(), default_params, len(run_params), output_subdirectory)
            run_params.append(params)
            
# =============================================================================
# Do something with the parameter dictionaries!
# print and optionally run them:
# =============================================================================
for params in run_params:
    print("*"*80)
    print("* Parameters: ")
    for k, v in params.items():
        print("{:25}{}".format(k, v))
    print("*"*80)
    if run_keras:
        # finally do some work!
        nt3b.run(params)

# =============================================================================
# Now gather up the results from output_subdirectory and repeat
# =============================================================================
if run_keras:
    new_data = get_nt3_data(output_dir, output_subdirectory)
    new_data.describe()
 
# =============================================================================
# Augment training data, update GPR model, generate new candidates ...
# =============================================================================

#    nt3_data = rd.NT3RunData(output_dir=output_dir,
#                               subdirectory=output_subdirectory) #,
#                               #pdtypes=pdtypes)
#    nt3_data.add_all()
#    new_data = nt3_data.dataframe
#    #new_data_dict = nt3_data.data
#    new_data.describe()