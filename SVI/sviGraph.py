import numpy as np
import matplotlib.pyplot as plt

# Define the SVI function
def svi(params, k):
    a, b, rho, m, sigma = params['a'], params['b'], params['rho'], params['m'], params['sig']
    return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))

# Define SVI parameters as a dictionary (equivalent to list in R)
svi_params = {'a': 0.04, 'b': 0.4, 'sig': 0.1, 'rho': -0.4, 'm': 0.1}

# Generate log-strike values
k_values = np.linspace(-1, 1, 400)

# Calculate implied variance using SVI for the first set of parameters
implied_variance = svi(svi_params, k_values)

# Plot the first SVI curve
plt.plot(k_values, implied_variance, color='red', label='Original Params')
plt.xlabel('Log-strike k')
plt.ylabel('Implied variance ' + r'$\sigma^2 T$')

# Update SVI parameters for the second curve
svi_params2 = svi_params.copy()
svi_params2['b'] = svi_params['b'] + 0.05

# Calculate implied variance using SVI for the second set of parameters
implied_variance2 = svi(svi_params2, k_values)

# Plot the second SVI curve
plt.plot(k_values, implied_variance2, color='blue', linestyle='--', label='Updated Params')

plt.legend()
plt.title('SVI Model')
plt.show()
