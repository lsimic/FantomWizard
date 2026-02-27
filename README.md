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
1. Select desired trimester  
2. For second trimester specify fetus orientation  
3. Specify fantom weight and height  
4. Specify the voxel size (used for the volume nodes, voxelized format and voxel segmentation)  
5. Specify what data should be generated
- Volume Segmentation node - voxel based segmentation  
- Polydata Segmentation node - mesh based segmentation  
- Voxelized form - exports the generated fantom in the voxelized format for furhter use  
6. (If enabled) Specify the output location for the voxelized form  
