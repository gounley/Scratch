#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 18 14:36:59 2017

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
#            P3B1
# =============================================================================

import os
import sys

# =============================================================================
# Add paths to Benchmarks to system paths to allow imports
# =============================================================================
    
file_path = os.path.dirname(os.path.realpath(__file__))

paths = {"common" : ['..', '..', 'Benchmarks', 'common'],
         "P1_common" : ['..', '..', 'Benchmarks', 'Pilot1', 'common'],
         "P1B1" : ['..', '..', 'Benchmarks', 'Pilot1', 'P1B1']
        }

for path in paths.values():
    lib_path = os.path.abspath(os.path.join(*[file_path]+path))
    sys.path.append(lib_path)


import logging
logging.basicConfig(filename='P1B1.log',level=logging.DEBUG)

# TODO: change the name to run_data 
# TODO: remove this unless run.x.x.x.json logs written by keras are being used
# import nt3_run_data as nt3d
import p1b1_baseline_keras2 as p1b1k2
import p1b1
#import run_data
import parameter_set as prs
import CategoricalKernel as ck

from collections import defaultdict, namedtuple
from math import pi

#from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from sklearn.model_selection import ParameterGrid, ParameterSampler

import pandas as pd
import numpy as np
import scipy as sp
from scipy.stats.distributions import expon

# data are correctly reshaped but warning is present anyway, 
#so suppress them all (bug in sklearn.optimize reported)
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning) 

# =============================================================================
# CONFIGURATION done here for now
# =============================================================================

# if True, parameter dictionaries will be sent to nt3_baseline_keras2
run_keras = True
plots = True

# Location of saved output
output_dir = os.path.join(file_path, 'save')
OUTPUT_SUBDIRECTORY = "experiment_0"

config_file_path = os.path.join(*[file_path]+paths["P1B1"])
CONFIG_FILE = os.path.join(config_file_path, 'p1b1_default_model.txt')
# read in global default parameter configuration
DEFAULT_PARAMS = p1b1.read_config_file(CONFIG_FILE)
# don't include points with ridiculously large losses, as defined here
# when fitting GPR model
MAX_LOSS = 5

PREFIX_SEP = "|"

# the target is validation_loss, could be training_loss or runtime_hours
TARGET = 'validation_loss'

# =============================================================================
# # see https://cran.r-project.org/web/packages/ParamHelpers/ParamHelpers.pdfmakeNum
# # the parameter names should match names of the arguments expected by the benchmark
# 
# # Current best val_corr: 0.96 for ae, 0.86 for vae
# # We are more interested in vae results
# 
# param.set <- makeParamSet(
#   # we optimize for ae and vae separately
#   makeDiscreteParam("model", values=c("ae", "vae")),
# 
#   # latent_dim impacts ae more than vae
#   makeDiscreteParam("latent_dim", values=c(2, 8, 32, 128, 512)),
# 
#   # use a subset of 978 landmark features only to speed up training
#   makeDiscreteParam("use_landmark_genes", values=c(True)),
# 
#   # large batch_size only makes sense when warmup_lr is on
#   makeDiscreteParam("batch_size", values=c(32, 64, 128, 256, 512, 1024)),
# 
#   # use consecutive 978-neuron layers to facilitate residual connections
#   makeDiscreteParam("dense", values=c("2000 600",
#                                       "978 978",
# 				      "978 978 978",
# 				      "978 978 978 978",
# 				      "978 978 978 978 978",
# 				      "978 978 978 978 978 978")),
# 
#   makeDiscreteParam("residual", values=c(True, False)),
# 
#   makeDiscreteParam("activation", values=c("relu", "sigmoid", "tanh")),
# 
#   makeDiscreteParam("optimizer", values=c("adam", "sgd", "rmsprop")),
# 
#   makeNumericParam("learning_rate", lower=0.00001, upper=0.1),
# 
#   makeDiscreteParam("reduce_lr", values=c(True, False)),
# 
#   makeDiscreteParam("warmup_lr", values=c(True, False)),
# 
#   makeNumericParam("drop", lower=0, upper=0.9),
# 
#   makeIntegerParam("epochs", lower=100, upper=200),
# )
# =============================================================================

activation = ["relu", "sigmoid", "tanh"]
#activation = ["softmax", "elu", "softplus", "softsign", "relu", "tanh", "sigmoid", "hard_sigmoid", "linear"]
batch_size = [16, 32, 64, 128, 256, 512, 1024]
#dense = ["1800 600",
#         "978 978",
#         "978 978 978",
#         "978 978 978 978",
#         "978 978 978 978 978",
#         "978 978 978 978 978 978"]
dense = [
 '[1800, 600]',
 '[978, 978, 978, 978, 978, 978]',
 '[978, 978, 978, 978, 978]',
 '[978, 978, 978, 978]',
 '[978, 978, 978]',
 '[978, 978]']
latent_dim = [2, 8, 32, 128, 512]
model = ["ae", "vae"]
residual = [0, 1]
optimizer = ["adam", "sgd", "rmsprop"]
#optimizer = ["adam", "sgd", "rmsprop", "adagrad", "adadelta","adamax","nadam"]
reduce_lr = [0, 1]
warmup_lr = [0, 1]

# probably add this in param_update... where is it used?
use_landmark_genes = True
      
# =============================================================================
# ParameterGrid used for initial keras runs
# =============================================================================
def p1b1_parameter_grid():
    """Utility function to encapsulate ParameterGrid definition"""
    
    gdict = {"activation" : activation,
             "batch_size" : batch_size,
             "dense" : dense,
             "drop" : [0.0, 0.50, 0.90],
             "epochs" : [10,20], #[100, 150, 200],
             "latent_dim" : [2,8, 32, 128, 512],
             "learning_rate" : [0.00001, 0.05, 0.1],
             "model" : ["ae", "vae"],
             "optimizer" : optimizer,
             "residual" : residual,
             "reduce_lr" : reduce_lr,
             "warmup_lr" : warmup_lr
            }
    
    pg = ParameterGrid(gdict)
    return pg

# =============================================================================
# ParameterGrid used for iteration, enumeration, and grid search
# =============================================================================
def p1b1_parameter_grid_optimize(num=50, fixed={}):
    """Utility function to encapsulate ParameterGrid definition
    
    num: number of points for numeric
    fixed: dictionary giving discrete values which are constant
    value should be supplied as a list with a single element
    ... consider using np.ogrid"""
    
    
    gdict = {"activation" : activation,
             "batch_size" : batch_size,
             "dense" : dense,
             "drop" : np.linspace(0.0, 0.9, num=num),
             "epochs" : np.arange(10, 21),
             "latent_dim" : [2, 8, 32, 128, 512],
             "learning_rate" : np.linspace(0.00001, 0.05, num=num),
             "model" : ["ae", "vae"],
             "optimizer" : optimizer,
             "residual" : residual,
             "reduce_lr" : reduce_lr,
             "warmup_lr" : warmup_lr
            }
    gdict.update(fixed)
    
    pg = ParameterGrid(gdict)
    return pg
# =============================================================================
# ParameterSet used for focus search after model fit
# =============================================================================
def p1b1_parameter_set(): 
    """Utility function to encapsulate ParameterSet definition"""
    
    ps = prs.ParameterSet()
 
    ps["activation"] = prs.DiscreteParameter(activation)
    ps["batch_size"] = prs.NumericListParameter(batch_size)
    ps["dense"] = prs.DiscreteParameter(dense)
    ps["drop"] = prs.NumericParameter(0.0, 0.9)
    ps["epochs"] = prs.IntegerParameter(10, 20) #100, 200)
    ps["latent_dim"] = prs.NumericListParameter(latent_dim)
    ps["learning_rate"] = prs.NumericParameter(0.00001, 0.1)
    ps["model"] = prs.DiscreteParameter(model)
    ps["optimizer"] = prs.DiscreteParameter(optimizer)
    ps["residual"] = prs.DiscreteParameter(residual)
    ps["reduce_lr"] = prs.DiscreteParameter(reduce_lr)
    ps["warmup_lr"] = prs.DiscreteParameter(warmup_lr)
    
#    # switching batch_size to NumericList to enforce integer validation
#    ps.add(prs.DiscreteParameter("activation", activation))
#    ps.add(prs.NumericListParameter("batch_size", batch_size))
#    ps.add(prs.DiscreteParameter("dense", dense))
#    ps.add(prs.NumericParameter("drop", 0.0, 0.9))
#    ps.add(prs.IntegerParameter("epochs",  10, 20)) #100, 200))
#    ps.add(prs.NumericListParameter("latent_dim", latent_dim))
#    ps.add(prs.NumericParameter("learning_rate", 0.00001, 0.1))
#    ps.add(prs.DiscreteParameter("model", model))
#    ps.add(prs.DiscreteParameter("optimizer", optimizer))
#    ps.add(prs.DiscreteParameter("residual", residual))
#    ps.add(prs.DiscreteParameter("reduce_lr", reduce_lr))
#    ps.add(prs.DiscreteParameter("warmup_lr", warmup_lr))
    
    return ps

class GPR_Model(object):
    """Given a dataframe, construct views for X, Y and dummy-coded factors"""
    def __init__(self, data_df, X_columns, factors=[], target=TARGET, 
                 prefix_sep=PREFIX_SEP):
        
        dfc_set = set(data_df.columns)
        xcol_set = set(X_columns)
        factor_set = set(factors)
        
        assert target in dfc_set, "Target column must be in dataframe"
        assert xcol_set.issubset(dfc_set), "X_columns must be in dataframe's columns"
        assert factor_set.issubset(dfc_set), "Factors must be in dataframe's columns"
        #assert set(factors).issubset(set(X_columns)), "Factors should be listed in X_columns"
        
        self.data = data_df
        self.factors = factors
        
        xcol_set = xcol_set | factor_set    # set union
        xcol_set.discard(target)
        
        # n.b. set is not a hashable type so make it a list
        X = data_df[list(xcol_set)]
        y = data_df[target]
        
        # Create auxiliary dataframe with dummy-coded indicators 
        if factors:
            #data_with_dummies = prs.DataFrameWithDummies(X, dummies=['shared_nnet_spec', 'ind_nnet_spec'])
            #Xd = data_with_dummies.dataframe
            Xd = pd.get_dummies(X, columns=factors, prefix_sep=PREFIX_SEP) if factors else X
        else:
            Xd = X
            
        continuous_columns = []
        factor_columns = defaultdict(list)
        factor_values = defaultdict(list)
        
        for i, name in enumerate(Xd.columns):
            n = name.split(PREFIX_SEP)
            n0 = n[0]
            if n0 in factors:
                factor_columns[n0].append(i)
                factor_values[n0].append(PREFIX_SEP.join(n[1:]))
            else:
                continuous_columns.append(i)
                
        # TODO: create a new parameter set, just for the factors
        ps_factor = prs.ParameterSet()
        for name, values in factor_values.items():
            #ps_factor.add(prs.DiscreteParameter(name, values))
            ps_factor[name] = prs.DiscreteParameter(values)
    
        #self.n_continuous = len(continuous_columns)
        self.continuous_columns = continuous_columns
        self.factor_columns = factor_columns
        self.parameter_set = ps_factor
        self.X = X
        self.Xd = Xd
        self.y = y
        
        # TODO: consider leaving these till later, and using hasattr to check
        self.gpr_ec = None
        self.gpr_mc = None
        self.gpr_uc = None
        
    def fit_EC(self, theta=0.1, alpha=0.01, n_restarts_optimizer=20):
       
        kernels = [ConstantKernel(1.0, (0.001, 1000.0))]
        
        # TODO: consider initializing with each variable's standard deviation
        kernel = ck.Projection(self.continuous_columns, name="continuous")
        kernels.append(kernel)
        # TODO: move this elsewhere!
    
        #model = "EC"

        for factor, columns in self.factor_columns.items():
            kernel = ck.ExchangeableCorrelation(len(columns), zeta=theta)
            kernel = ck.Projection(columns, name=factor, kernel=kernel)
            kernels.append(kernel)
        
        kernel = ck.Tensor(kernels)
        
        print("Exchangeable Correlation Kernel for Gaussian Process Regression")
        print(kernel)
        logging.debug("Exchangeable Correlation Kernel for Gaussian Process Regression\n{}".format(kernel))
        gpr = GaussianProcessRegressor(kernel=kernel,
                                       alpha=alpha,
                                       normalize_y=True,
                                       n_restarts_optimizer=n_restarts_optimizer)
        #gpr = GaussianProcessRegressor(kernel=k, alpha=0.001, normalize_y=True)
        
        gpr.fit(self.Xd, self.y)
        
        self.gpr_ec = gpr

    def fit_MC(self, alpha=0.01, n_restarts_optimizer=20):
       
        kernels = [ConstantKernel(1.0, (0.001, 1000.0))]
        
        # TODO: consider initializing with each variable's standard deviation
        kernel = ck.Projection(self.continuous_columns, name="continuous")
        kernels.append(kernel)
        # TODO: move this elsewhere!
    
        ec = self.gpr_ec
        params = ec.kernel_.get_params() if ec else {}
    
        found = find_by_name(params)
    
        ec_kernel = {}
        for k, name in found.items():
            if name in self.factors:
                # factor_columns already knows columns
                #columns = params.get("{}__columns".format(k), [])
                ec_kernel[name] = params.get("{}__kernel".format(k), None)  
                    
        for factor, columns in self.factor_columns.items():
            dim = len(columns)
            try:
                theta = ec_kernel[factor].initialize_multiplicative_correlation()
                print("Initializing factor '{}' with {}".format(factor, theta))
            except:
                print("Whoops! Factor {} not found".format(factor))
                theta = np.array([theta] * len(columns))
            kernel = ck.MultiplicativeCorrelation(dim, zeta=theta)
            kernel = ck.Projection(columns, name=factor, kernel=kernel)

            kernels.append(kernel)
        
        kernel = ck.Tensor(kernels)
        print("Multiplicative Correlation Kernel for Gaussian Process Regression")
        print(kernel)
        logging.debug("Multiplicative Correlation Kernel for Gaussian Process Regression\n{}".format(kernel))
        
        gpr = GaussianProcessRegressor(kernel=kernel,
                                       alpha=alpha,
                                       normalize_y=True,
                                       n_restarts_optimizer=20)        
        gpr.fit(self.Xd, self.y)

        logging.debug("Fit Gaussian Process Regression:\n{}".format(gpr.kernel_.get_params())) 
        report = name_report(gpr, self.factors)
        logging.info("Unrestrictive Correlation Kernel for Gaussian Process Regression\n{}".format(report))
        
        self.gpr_mc = gpr
        
    def fit_UC(self, theta=None, alpha=0.01, n_restarts_optimizer=20):
       
        kernels = [ConstantKernel(1.0, (0.001, 1000.0))]
        
        # TODO: consider initializing with each variable's standard deviation
        kernel = ck.Projection(self.continuous_columns, name="continuous")
        kernels.append(kernel)
        # TODO: move this elsewhere!
    
        mc = self.gpr_mc
        
        params = mc.kernel_.get_params() if mc else {}
    
        found = find_by_name(params)
    
        uc_kernel = {}
        for k, name in found.items():
            if name in self.factors:
                # factor_columns already knows columns
                #columns = params.get("{}__columns".format(k), [])
                uc_kernel[name] = params.get("{}__kernel".format(k), None)  
                    
        for factor, columns in self.factor_columns.items():
            dim = len(columns)
            m = dim * (dim - 1) //2
            if np.iterable(theta) and (len(theta) == m):
                # use supplied theta
                pass
            else:
                try:
                    theta = uc_kernel[factor].initialize_unrestrictive_correlation()
                except:
                    print("Whoops! Factor {} not found".format(factor))
                    theta = np.array([0.1] * m)
            
            kernel = ck.UnrestrictiveCorrelation(dim, zeta=theta)
            kernel = ck.Projection(columns, name=factor, kernel=kernel)
            kernels.append(kernel)
        
        kernel = ck.Tensor(kernels)
        print("Multiplicative Correlation Kernel for Gaussian Process Regression")
        print(kernel)
        logging.debug("Unrestrictive Correlation Kernel for Gaussian Process Regression\n{}".format(kernel))
        
        gpr = GaussianProcessRegressor(kernel=kernel,
                                       alpha=alpha,
                                       normalize_y=True,
                                       n_restarts_optimizer=20)
        #gpr = GaussianProcessRegressor(kernel=k, alpha=0.001, normalize_y=True)
        
        gpr.fit(self.Xd, self.y)
        # n.b. could scale y but for now handle y with normalize_y in GPR
        
        logging.debug("Fit Gaussian Process Regression:\n{}".format(gpr.kernel_.get_params())) 
        report = name_report(gpr, self.factors)
        logging.info("Unrestrictive Correlation Kernel for Gaussian Process Regression\n{}".format(report))
        self.gpr_uc = gpr

    def fit(self, theta=0.1, alpha=0.01, n_restarts_optimizer=20):
        self.fit_EC(theta=theta, alpha=alpha, n_restarts_optimizer=n_restarts_optimizer)
        # use initial values provided by EC, then by MC
        self.fit_MC(alpha=alpha, n_restarts_optimizer=n_restarts_optimizer)
        self.fit_UC(alpha=alpha, n_restarts_optimizer=n_restarts_optimizer)

    def dummy_data_to_dict(self, datum):
        columns = self.Xd.columns
        return {col : val for col, val in zip(columns, datum)}

    def decode_dummies(self, X, param_set):
        #columns = self.Xd.columns
        decoded = []
        for i in range(X.shape[0]):
            x = X.iloc[i]
            #d = {col : val for col, val in zip(columns, x)}
            d = self.dummy_data_to_dict(x)
            params = param_set.decode_dummies(d)
            decoded.append(params)
        return decoded

    def predict_penalized(self, gpr, gamma=1.0, delta=1.0):
        def factor_penalty(X, columns):
            W = X[columns]
            return gamma*(np.linalg.norm(W, ord=2) - 1.0)**2 + delta*(np.linalg.norm(W, ord=1) - 1)**2
        
        return lambda X : gpr.predict(X) + sum(factor_penalty(X, columns) for columns in self.factor_columns.values())
        
    def optimize(self, gamma=1.0, delta=1.0, gpr=None, Xd=None):
        """gpr should be self.gpr_uc, _mc, or _ec..."""
        if gpr is None:
            gpr = self.gpr_uc
        if Xd is None:
            Xd = self.Xd
            
        columns = Xd.columns
            
        lower_bounds = Xd.min(axis=0)
        upper_bounds = Xd.max(axis=0)
        
        bounds = [(lower, upper) for lower, upper in zip(lower_bounds, upper_bounds)]

        result_data = defaultdict(list)
        for i in range(Xd.shape[0]):
            # TODO: pick a float between 0 and 1 for each value
            # rescale using bounds as range, i.e. r * (upper - lower) + lower
            start_val = Xd.iloc[i].as_matrix().reshape(-1,1)
            #start_val = np.array(start_val).reshape(-1, 1)
            #start_val = Xs[yidxmin].reshape(-1,  1)
            # Fit the GPR model
            predict = self.predict_penalized(gpr)
            result = sp.optimize.minimize(predict, start_val, method='L-BFGS-B', bounds=bounds)
            rx = result.x
            pred = gpr.predict(result.x)
            for col, val in zip(columns, rx):
                result_data[col].append(val)
            # pred is an ndarray with shape (1,) so unpack it
            result_data['gpr_optimum'].append(pred[0])
        for k , v in result_data.items():
            logging.debug("{} {}".format(k, len(v)))
        # the dictionary will need to be decoded by a ParameterSet object
        result_data = pd.DataFrame(result_data)
        return result_data
    
    def optimize_recommend(self, param_set, gamma=1.0, delta=1.0,
                           gpr=None, Xd=None,
                           return_data=False):
        """Optimizes GPR model, using each data point as initial value
        
        Returns one recommendation for each point, 
        however, these may all be the same if they all converge to the
        global minimum.  The results are decoded into parameter sets."""
        x = self.optimize(gamma=gamma, delta=delta, gpr=gpr, Xd=Xd)
        paramdictlist = self.decode_dummies(x, param_set)
        if return_data:
            return paramdictlist, x
        else:
            return paramdictlist

    def LCB(self, n_sample, gpr=None, Xd=None):
        if gpr is None:
            gpr = self.gpr_uc
        if gpr is None:
            gpr = self.gpr_mc
        if gpr is None:
            gpr = self.gpr_ec
        if Xd is None:
            Xd = self.Xd
        preds = gpr.predict(Xd, return_std=True)
        preds = pd.DataFrame({"prediction" : preds[0], "std_dev" : preds[1]})
        # n.b. lambda is a keyword so change vector of values to alpha
        alpha = ParameterSampler({ "alpha" : expon()}, n_iter=n_sample)
        lcb = pd.DataFrame({"lcb_{}".format(i) : \
                            preds.prediction - \
                            (li["alpha"] * preds.std_dev) \
                            for i, li in enumerate(alpha)})
        # TODO: include X in lcb, to look up parameters from selected values
        return lcb

    def LCB_recommend(self, n_recommend, param_set, n_sample=10,
                      gpr=None, Xd=None,
                      return_data=False):
        """Lower Confidence Bound recommendations for GPR model"""
        
        if gpr is None:
            gpr = self.gpr_uc
        if gpr is None:
            gpr = self.gpr_mc
        if gpr is None:
            gpr = self.gpr_ec
        if Xd is None:
            Xd = self.Xd
        lcb = self.LCB(n_sample=n_sample, gpr=gpr, Xd=None)
        lcb['minimum'] = lcb.min(axis=1)
        lcb.sort_values(by='minimum', inplace=True)
        Xdmin = Xd.iloc[lcb.index[:n_recommend]]
        recommend = self.decode_dummies(Xdmin, param_set)
#        recommend = []
#        for i in range(Xdmin.shape[0]):
#            x = Xdmin.iloc[i]
#            recommend.append(self.decode_dummies(x, param_set))
        if return_data:
            return recommend, Xdmin
        else:
            return recommend

# =============================================================================
# Some reports that can stay here until they find a better home
# =============================================================================
def report(gpr):
    for k, ker in gpr.kernel_.get_params().items():
        try:
            print(k)
            print(ker)
            print(ker.theta)
            print(ker.correlation)
        except:
            pass

def find_by_name(params):
    """Finds keys which have 'name' parameters, and associated name
    
    Currently only Projection kernels have names
    Nested kernel can be obtained from parameter "{}__kernel".format(key)
    """
    found = {}
    for k, v in params.items():
        split = k.split("__", 1)
        name = split[1] if len(split) > 1 else ""
        if name == 'name':
            found[split[0]] = v
        #print(k, split, v)
    return found

def name_report(gpr, factors):
    """Report correlations for factors.
    
    Assumes the factor kernel can be found by searching Projection kernels
    by name."""
    report = []
    params = gpr.kernel_.get_params()
    found = find_by_name(params)
    report.append("*"*50)
    for key, name in found.items():
        if name in factors:  
            try:
                report.append(name)
                report.append(str(params["{}__kernel".format(key)].correlation))
                report.append("*"*50)
            except:
                pass
    return "\n".join(report)

def param_update(params, default_params, run_id, output_subdirectory='exp'):
    """ChainMap in Python 3 would be a good replacement"""
    run_params = default_params.copy()
    run_params.update(params)
    run_params['save'] = 'save/{}'.format(output_subdirectory)
    #run_params['solr_root'] = "http://localhost:8983/solr"
    run_params['run_id'] = "run.{}.json".format(run_id)
    # TODO: find a better workaround [FIXED in ParameterSet now ?]
    # batch_size is a DiscreteParameter but not dummy-coded
    # does not know to validate as integer
    #run_params['batch_size'] = int(run_params.get('batch_size', 16))
    # TODO: should these be in default_params?
    run_params['alpha_dropout'] = run_params.get('alpha_dropout', 0)
    run_params['use_landmark_genes'] = run_params.get('use_landmark_genes', True)
    run_params['logfile'] = 'placeholder.log' #run_params.get('logfile', False)
    run_params['verbose'] = False
    run_params['shuffle'] = run_params.get('shuffle', True)
    run_params['datatype'] = 'f32' # DEFAULT_DATATYPE
    return run_params

def focus_search(params,
                 default_params,
                 output_subdirectory,
                 run_params=[],
                 n_recommend=1,
                 degree=1):
    for i in range(degree):
        focus = ps.focus(params)
    #run_params = []
    # low-rent strategy for generating a unique id: use length of run_params
    for j in range(n_recommend):
        params = param_update(focus.draw(), default_params, len(run_params), output_subdirectory)
        run_params.append(params)
    return run_params
                
                
if __name__ == "__main__":
    # parameter grid would be used to generate initial data
    # not currently used because data are read from cached .csv file
    pg = p1b1_parameter_grid()
    ps = p1b1_parameter_set()
    
    print(pg)
    print(ps)
    
    p1b1csv = "P1B1_data.csv"
    p1b1_data = pd.read_csv(p1b1csv)
    valid = p1b1_data.validation_loss.notnull()
    p1b1_data = p1b1_data[valid]
    
    print(p1b1_data.describe())
       
# =============================================================================
# After inspecting the data, it seems that the overwhelming majority are < 1
# but there are some really big ones in there
# =============================================================================
    p1b1_data = p1b1_data[p1b1_data.validation_loss < 1]

# =============================================================================
# TODO: use a train/test split, cross-validate model, compute score
# =============================================================================

# =============================================================================
# To work with a subset of the 1046 points remaining after the above:
# =============================================================================
    subset = [i for i in range(len(p1b1_data)) if i % 5 == 0]
    p1b1_data = p1b1_data.iloc[subset]


    data_columns = [
             'drop',
             'optimizer',
             'warmup_lr',
             'activation',
             'residual',
             'batch_size',
             'epochs',
             'dense',
             'latent_dim',
             'reduce_lr',
             'model',
             'learning_rate',
             'run_id',
             'training_loss',
             'validation_loss',
             'runtime_hours',
             'run_id.1',
             'training_loss.1',
             'validation_loss.1',
             'runtime_hours.1'
             ]
    X_columns = [
             'drop',
             'batch_size',
             'epochs',
             'learning_rate'
             ]
    factors =[
             'optimizer',
             'warmup_lr',
             'activation',
             'residual',
             'dense',
             'latent_dim',
             'reduce_lr',
             'model'
             ]
    
# =============================================================================
#  SEE NOTE in ParameterSet.R:
#    Current best val_corr: 0.96 for ae, 0.86 for vae
#    We are more interested in vae results
# =============================================================================
    restrict_model = 'vae' # None or False or 'vae' or 'ae'
    if restrict_model in ('ae', 'vae'):
        p1b1_data = p1b1_data[p1b1_data.model == restrict_model]
        factors.remove('model')
    
    # try a smaller problmen
    #factors = ['dense', 'model', 'warmup_lr', 'reduce_lr']
    assert all(x in data_columns for x in X_columns), "invalid column"
    
    gpr_model = GPR_Model(p1b1_data, X_columns, factors)
    gpr_model.fit_EC()
    gpr_model.fit_MC()
    gpr_model.fit_UC()
    # equivalent to : gpr_model.fit()
    
    print("\nExchangeable Correlations")
    report(gpr_model.gpr_ec)
    print("\nMultiplicative Correlations")
    report(gpr_model.gpr_mc)
    print("\nUnrestrictive Correlations")
    report(gpr_model.gpr_uc)
    
    print("\nExchangeable Correlations")
    print(name_report(gpr_model.gpr_ec, factors))
    print("\nMultiplicative Correlations")
    print(name_report(gpr_model.gpr_mc, factors))
    print("\nUnrestrictive Correlations")
    print(name_report(gpr_model.gpr_uc, factors))
    
  
    lcb_rec = gpr_model.LCB_recommend(10, ps)
    opt_rec = gpr_model.optimize_recommend(ps)
    
    default_params = p1b1.read_config_file("p1b1_default_model.txt")
    # .run calls .keras_default_config
    #keras_defaults = p1_common.keras_default_config()    
    # because we are interested in vae results
    if restrict_model in ('ae', 'vae'):
        default_params.update({ 'model' : restrict_model })
    
    # randomize draws in the vicinity of LCB points, since the original
    # points have already been evaluated
    
    # send opt and lcb recommendations to different subdirectories
    # to facilitate strategy comparison

    run_params = []
    # len(run_parsms) is used to generate unique ids of the form run.0.json
    for param_dict in opt_rec:
        run_params.append(param_update(param_dict, default_params,
                                       len(run_params), "opt"))
        
    # note focus_search calls param_update
    for param_dict in lcb_rec:
        run_params = focus_search(param_dict, default_params, "lcb", run_params,
                                  n_recommend=1, degree=5)
    for params in run_params[:5]:
        print(params)

    import json
    with open("p1b1_recommend.json", "w") as jsonfile:
        json.dump(params, jsonfile)
    
    