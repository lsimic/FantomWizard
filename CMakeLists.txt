cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(FantomWizard)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.github.com/lsimic/SlicerFantomWizard")
set(EXTENSION_CONTRIBUTORS "Luka Simic")
set(EXTENSION_DESCRIPTION "Create Fantom")
set(EXTENSION_ICONURL "https://www.github.com/lsimic/SlicerFantomWizard/FantomWizard.png")
set(EXTENSION_SCREENSHOTURLS "https://www.github.com/lsimic/SlicerFantomWizard/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CreateFantomModule)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
