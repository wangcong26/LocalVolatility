import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize


# The Stochastic Volatility Inspired (SVI) model is often used to fit an implied volatility smile or surface. The SVI model describes
# implied volatility as a function of the log-moneyness, defined as k=ln(K/F), where K is the option strike price and F is the forward price of the asset.

# Define the raw SVI function
def svi_raw(params, k):
    a, b, rho, m, sigma = params
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma ** 2))


# Objective function to minimize (least squares)
def objective(params, k, iv):
    return np.sum((svi_raw(params, k) - iv) ** 2)


# Synthetic implied volatility data (replace this with market data)
k_values = np.linspace(-0.2, 0.2, 100)  # log-moneyness
true_params = [0.04, 0.2, -0.3, 0.05, 0.1]
# true_params = [-0.40998372001772, 0.13308181151379, 0.35858898335748, 0.30602086142471, 0.41531878803777]
iv_values = svi_raw(true_params, k_values) + np.random.normal(0, 0.005, size=len(k_values))  # Synthetic IV with some noise

# Initial guess for parameters
initial_guess = [0.04, 0.2, -0.3, 0.05, 0.1]

# Parameter bounds
bounds = [(0, 1), (0, 1), (-1, 1), (-1, 1), (0, 1)]

# Perform the optimization to fit the SVI model
result = minimize(objective, initial_guess, args=(k_values, iv_values), bounds=bounds)

# Extract fitted parameters
fitted_params = result.x
print("Fitted Parameters:", fitted_params)

# Plot actual vs fitted implied volatility
plt.scatter(k_values, iv_values, label='Actual', s=5)
plt.plot(k_values, svi_raw(fitted_params, k_values), label='Fitted', linewidth=2)
plt.xlabel('Log-Moneyness')
plt.ylabel('Implied Volatility')
plt.title('SVI Fitting')
plt.legend()
plt.show()
