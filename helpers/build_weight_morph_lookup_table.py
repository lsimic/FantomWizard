# Small helper script
# iterates over the scaled objects and morphs, and builds a lookup table
# the lookup table is used to map desired weight + height combination
# to the appropriate morph value. 

import vtk
import json

def readVtkPolyObjectFromGltf(gltfPath):
  reader = vtk.vtkGLTFReader() 
  reader.SetFileName(gltfPath)
  reader.Update()
  vtkPolyObject = reader.GetOutput().NewIterator().GetCurrentDataObject()
  return vtkPolyObject

def main(basePath):
  outputArray = []

  # do the height blending first, going from min->max possible height
  for i in range(-10, 11):
    heightBlendFactor = i / 10
    print("processing mesh with factor " + str(heightBlendFactor))

    # load base object
    polyObjectBase = readVtkPolyObjectFromGltf(basePath + "/fantom_base/soft_tissues.glb")
    pointsObjectBase = polyObjectBase.GetPoints()

    # load scaled object
    if heightBlendFactor > 0:
      polyObjectScaled = readVtkPolyObjectFromGltf(basePath + "/fantom_scaled_up/soft_tissues.glb")
    else:
      polyObjectScaled = readVtkPolyObjectFromGltf(basePath + "/fantom_scaled_down/soft_tissues.glb")
    pointsObjectScaled = polyObjectScaled.GetPoints()

    # perform scaling based on height.
    for pointIndex in range(pointsObjectBase.GetNumberOfPoints()):
      pointBase = pointsObjectBase.GetPoint(pointIndex)
      pointScaled = pointsObjectScaled.GetPoint(pointIndex)
      x = pointBase[0] + abs(heightBlendFactor) * (pointScaled[0] - pointBase[0])
      y = pointBase[1] + abs(heightBlendFactor) * (pointScaled[1] - pointBase[1])
      z = pointBase[2] + abs(heightBlendFactor) * (pointScaled[2] - pointBase[2])
      pointsObjectScaled.SetPoint(pointIndex, x, y, z)
    
    # mark scaled object points as modified...
    pointsObjectScaled.Modified()

    # create a copy of height scaled points to use as basis for weight scaling
    pointsObjectCopy = vtk.vtkPoints()
    pointsObjectCopy.DeepCopy(polyObjectScaled.GetPoints())

    # with the height scaled, get the height value for current blend factor.
    # computed as bbmax.z - bbmin.z *0.1 to convert from mm to cm
    outputHeight = (polyObjectScaled.GetBounds()[5] - polyObjectScaled.GetBounds()[4]) * 0.1
    outputHeightBlendFactor = heightBlendFactor

    # store output weight and blend factor for each checked factor value in range (-1, 1)
    outputWeightsArray = []
    outputWeightBlendFactorsArray = []

    # do the weight blending for the current height.
    for j in range(-10, 11):
      weightBlendFactor = j / 10

      # load object with increased (or decreased) weight depending on the fac value.
      if weightBlendFactor > 0:
        polyObjectWeighted = readVtkPolyObjectFromGltf(basePath + "/fantom_weight_up/soft_tissues.glb")
      else:
        polyObjectWeighted = readVtkPolyObjectFromGltf(basePath + "/fantom_weight_down/soft_tissues.glb")
      pointsObjectWeighted = polyObjectWeighted.GetPoints()

      # perform scaling based on height
      pointsObjectScaled = polyObjectScaled.GetPoints()
      for pointIndex in range(pointsObjectBase.GetNumberOfPoints()):
        pointBase = pointsObjectBase.GetPoint(pointIndex)
        pointWeighted = pointsObjectWeighted.GetPoint(pointIndex)
        pointScaledHeight = pointsObjectCopy.GetPoint(pointIndex)
        x = pointScaledHeight[0] + abs(weightBlendFactor) * (pointWeighted[0] - pointBase[0])
        y = pointScaledHeight[1] + abs(weightBlendFactor) * (pointWeighted[1] - pointBase[1])
        z = pointScaledHeight[2] + abs(weightBlendFactor) * (pointWeighted[2] - pointBase[2])
        pointsObjectScaled.SetPoint(pointIndex, x, y, z)
        
      # mark scaled object points as modified...
      pointsObjectScaled.Modified()

      # compute volume of final scaled object (height and weight scaled)
      massProperties = vtk.vtkMassProperties()
      massProperties.SetInputData(polyObjectScaled)
      massProperties.Update()
      outputVolume = massProperties.GetVolume()

      # append weight and blending factor to array.
      outputWeightBlendFactor = weightBlendFactor
      # use 0.98 g/cm3, 0.001 is to convert from g to kg. 
      # second 0.001 is to convert from mm3 to cm3
      outputWeight = 0.001 * 0.001 * outputVolume * 0.97 
      outputWeightsArray.append(outputWeight)
      outputWeightBlendFactorsArray.append(outputWeightBlendFactor)
    
    # build output dictionary object for this height
    outputDict = dict()
    outputDict["height"] = outputHeight
    outputDict["height_blend_factor"] = outputHeightBlendFactor
    outputDict["weights"] = outputWeightsArray
    outputDict["weight_blend_factors"] = outputWeightBlendFactorsArray

    # append to final array
    outputArray.append(outputDict)
  
  # store the output array as json
  with open(basePath + "/_morph_lookup_table.json", "w") as f:
    json.dump(outputArray, f, indent=2)

# replace this with the correct path...
main("/home/Luka/Work/fantom/FantomWizard/CreateFantomModule/Resources/Data/1ts")
main("/home/Luka/Work/fantom/FantomWizard/CreateFantomModule/Resources/Data/2ts")
main("/home/Luka/Work/fantom/FantomWizard/CreateFantomModule/Resources/Data/2ts_head")
main("/home/Luka/Work/fantom/FantomWizard/CreateFantomModule/Resources/Data/3ts")