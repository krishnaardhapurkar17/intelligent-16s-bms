
import pybamm

print("=" * 55)
print("LFP BATTERY PARAMETER INSPECTION")
print("=" * 55)

# Load the published LFP parameter set
parameters = pybamm.ParameterValues("Prada2013")

print("\nParameter set: Prada2013")
print("PyBaMM version:", pybamm.__version__)

# Display important cell parameters
important_parameters = [
    "Nominal cell capacity [A.h]",
    "Current function [A]",
    "Lower voltage cut-off [V]",
    "Upper voltage cut-off [V]",
    "Ambient temperature [K]",
    "Initial temperature [K]",
    "Initial concentration in electrolyte [mol.m-3]",
]

print("\nIMPORTANT PARAMETERS")

for name in important_parameters:
    print(f"{name}: {parameters[name]}")

# Create the SPMe model
model = pybamm.lithium_ion.SPMe()

print("\nBuilding SPMe model...")

simulation = pybamm.Simulation(
    model,
    parameter_values=parameters
)

simulation.build()

print("\nSPMe model successfully built.")

print("\nLFP PARAMETER INSPECTION COMPLETE")
