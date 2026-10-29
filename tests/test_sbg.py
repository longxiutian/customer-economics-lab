"""Independent distribution and censoring checks for the inference mechanism."""
import numpy as np
import pandas as pd
import pytest
from scipy.special import betaln, gammaln
from cohort_lab.model import sbg_survival, _retention_features, _hazard_draws, _sbg_parameters


def test_conditional_hazard_product_equals_beta_survival():
    for alpha,beta in [(1.08,3.67),(.7,12),(2,5)]:
        age=np.arange(25)
        expected=np.r_[1.,np.cumprod(1-alpha/(alpha+beta+age[1:]-1))]
        np.testing.assert_allclose(sbg_survival(alpha,beta,age),expected,rtol=1e-12,atol=1e-14)
        assert np.all(np.diff(expected)<0)


def test_aggregated_and_individual_likelihoods_agree_up_to_count_combinatorics():
    alpha,beta=1.08,3.67
    # Individual paths: churn on renewals 1,2,2,4; three right-censored after 4.
    events=np.array([1,2,2,4]); censored=3
    individual=sum(betaln(alpha+1,beta+t-1)-betaln(alpha,beta) for t in events)
    individual+=censored*(betaln(alpha,beta+4)-betaln(alpha,beta))
    n=7; aggregate=0.; comb=0.
    for t in range(1,5):
        d=int((events==t).sum()); h=alpha/(alpha+beta+t-1)
        aggregate+=d*np.log(h)+(n-d)*np.log1p(-h)
        comb+=gammaln(n+1)-gammaln(d+1)-gammaln(n-d+1)
        n-=d
    assert aggregate==pytest.approx(individual,abs=1e-12)
    # A count-valued Binomial likelihood additionally counts equivalent paths.
    assert np.isfinite(aggregate+comb)


def test_observed_feature_whitelist_ignores_latent_truth_and_post_purchase_data():
    f=pd.DataFrame({'cohort_index':[0,23],'primary_need':['save_time','build_skill'],'channel':['search','partner']})
    baseline=_retention_features(f)
    changed=f.assign(theta=[.99,.01],latent_class=['bad','good'],future_value=[-100,9999],engagement=[0,999])
    for a,b in zip(baseline,_retention_features(changed)): np.testing.assert_array_equal(a,b)


def test_concentration_controls_residual_heterogeneity_at_same_mean():
    mu=.2
    variances=[mu*(1-mu)/(phi+1) for phi in [2,20]]
    assert variances[0]>variances[1]
    # Identical initial churn rates need not imply identical full retention curves.
    assert sbg_survival(mu*2,(1-mu)*2,12)>sbg_survival(mu*20,(1-mu)*20,12)


def test_disperse_strategy_implements_numpyro_initialization_protocol():
    import jax
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer.util import initialize_model
    from cohort_lab.model import _dispersed_initial_strategy
    def specification():
        scale=numpyro.sample('scale',dist.HalfNormal(1.))
        beta=numpyro.sample('beta',dist.Normal(0.,1.))
        numpyro.sample('obs',dist.Normal(beta,scale),obs=1.)
    strategy=_dispersed_initial_strategy({'scale':.5,'beta':0.})
    result=initialize_model(jax.random.PRNGKey(1),specification,init_strategy=strategy)
    assert np.isfinite(float(result.param_info.potential_energy))
