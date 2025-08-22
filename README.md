# FantomWizard

## Notes
Tested only with Slicer 5.8.1 on Linux

## Installation instructions
Clone this repository  
Open Slicer  
Go to Edit - Application Settings - Modules  
Drag and Drop the "CreateFantomModule" folder into "Additional module paths"  
The tool should become available under Wizards - Create Fantom  

## Usage Instructions
Select desired trimester  
For second trimester specify fetus orientation  
Specify fantom weight and height
Specify the voxel size (used for DICOM, voxelized format and voxel segmentation)  
Specify what data should be generated  
- Volume Segmentation node - voxel based segmentation  
- Polydata Segmentation node - mesh based segmentation  
- Voxelized form - exports the generated fantom in the voxelized format for furhter use  
(If enabled) Specify the output location for the voxelized form  
