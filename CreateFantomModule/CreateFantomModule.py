import logging
from typing import Annotated, Optional
import os
import json
import math
import vtk
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
  parameterNodeWrapper,
  WithinRange,
)
from slicer import vtkMRMLScalarVolumeNode
import sys

def getTrimesterHeadString(trimester, head):
  if trimester == 1:
    return "1ts"
  if trimester == 2:
    if head:
      return "2ts_head"
    else:
      return "2ts"
  if trimester == 3:
    return "3ts"
  raise Exception("invalid trimester value")

def GetMorphLookupTable(trimester, head):
  jsonPath = os.path.dirname(os.path.abspath(__file__))
  jsonPath = jsonPath + "/Resources/Data/" + getTrimesterHeadString(trimester, head) + "/_morph_lookup_table.json"
  with open(jsonPath) as jsonFile:
    jsonData = json.load(jsonFile)
    return jsonData
  return None  

def GetHeightRangeFromLookupTable(trimester, head):
  lookupTable = GetMorphLookupTable(trimester, head)
  first = lookupTable[0]
  last = lookupTable[len(lookupTable) - 1]
  return (math.ceil(first["height"]), math.floor(last["height"]))

def GetWeightRangeFromLookupTable(trimester, head, height):
  jsonPath = os.path.dirname(os.path.abspath(__file__))
  jsonPath = jsonPath + "/Resources/Data/" + getTrimesterHeadString(trimester, head) + "/_morph_lookup_table.json"
  with open(jsonPath) as jsonFile:
    jsonData = json.load(jsonFile)
    for i in range (0, len(jsonData) - 1):
      currentVal = jsonData[i]
      nextVal = jsonData[i + 1]
      if currentVal["height"] <= height and nextVal["height"] >= height:
        # blend factor for heights...
        blend = (height - currentVal["height"]) / (nextVal["height"] - currentVal["height"])
        minWeightCurrent = currentVal["weights"][0]
        maxWeightCurrent = currentVal["weights"][len(nextVal["weights"]) - 1]
        minWeightNext = nextVal["weights"][0]
        maxWeightNext = nextVal["weights"][len(nextVal["weights"]) - 1]
        minValue = minWeightCurrent + blend * (minWeightNext - minWeightCurrent)
        maxValue = maxWeightCurrent + blend * (maxWeightNext - maxWeightCurrent)
        return (math.ceil(minValue), math.floor(maxValue))
  return None

def ClampValue(val, min, max):
  if val < min:
    return min
  if val > max:
    return max
  return val

class CreateFantomModule(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = _("Create Fantom")
    self.parent.categories = [translate("qSlicerAbstractCoreModule", "Wizards")]
    self.parent.contributors = ["Luka Simic"]
    self.parent.helpText = _("""Create Fantom. More information on <a href="https://github.com/lsimic/FantomWizard">GitHub</a>. """)
    self.parent.acknowledgementText = _("Developed in collaboration with KBC Osijek")

@parameterNodeWrapper
class CreateFantomModuleParameterNode:
  """
  The parameters needed by module.
  trimester - The trimester of the model.
  height - The height of the model (in cm).
  weight - The weight of the model (in kg).
  voxelSizeSaggital - The voxel size (in mm).
  voxelSizeCoronal - The voxel size (in mm).
  voxelSizeAxial - The voxel size (in mm).
  """
  trimester: Annotated[int, WithinRange(1, 3)] = 1
  height: Annotated[float, WithinRange(69.35, 109.35)] = 89.0
  weight: Annotated[float, WithinRange(30, 70)] = 50
  voxelSizeSaggital: Annotated[float, WithinRange(0.2, 2.0)] = 1.0
  voxelSizeCoronal: Annotated[float, WithinRange(0.2, 2.0)] = 1.0
  voxelSizeAxial: Annotated[float, WithinRange(0.2, 2.0)] = 1.0

class CreateFantomModuleWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None) -> None:
    """Called when the user opens the module the first time and the widget is initialized."""
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._parameterNodeGuiTag = None

  def setup(self) -> None:
    """Called when the user opens the module the first time and the widget is initialized."""
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath("UI/CreateFantomModule.ui"))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = CreateFantomModuleLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Buttons
    self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
    self.ui.heightWidget.connect("valueChanged(double)", self.onHeightChange)
    self.ui.trimesterWidget.connect("valueChanged(int)", self.onTrimesterOrHeadChange)
    self.ui.headDownCheckBox.connect("stateChanged(int)", self.onTrimesterOrHeadChange)
    self.ui.exportVoxelizedCheckBox.connect("stateChanged(int)", self.onExportVoxelizedChange)

    # make sure that the values are in a valid range
    self.onTrimesterOrHeadChange()

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

    # make sure that the folder selector is correctly enabled/disabled
    self.onExportVoxelizedChange()

  def cleanup(self) -> None:
    """Called when the application closes and the module widget is destroyed."""
    self.removeObservers()

  def enter(self) -> None:
    """Called each time the user opens this module."""
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self) -> None:
    """Called each time the user opens a different module."""
    # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
    if self._parameterNode:
      self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
      self._parameterNodeGuiTag = None

  def onSceneStartClose(self, caller, event) -> None:
    """Called just before the scene is closed."""
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event) -> None:
    """Called just after the scene is closed."""
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self) -> None:
    """Ensure parameter node exists and observed."""
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode: Optional[CreateFantomModuleParameterNode]) -> None:
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if self._parameterNode:
      self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
    self._parameterNode = inputParameterNode
    if self._parameterNode:
      # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
      # ui element that needs connection.
      self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)

  def onTrimesterOrHeadChange(self) -> None:
    # if trimester changes, this can change the height range
    # validate that the height is within the supported range and clamp if required. 
    trimester = self.ui.trimesterWidget.value
    headDown = self.ui.headDownCheckBox.checked
    minHeight, maxHeight = GetHeightRangeFromLookupTable(trimester, headDown)
    self.ui.heightWidget.minimum = minHeight
    self.ui.heightWidget.maximum = maxHeight
    if self.ui.heightWidget.value < minHeight:
      self.ui.heightWidget.value = minHeight
    if self.ui.heightWidget.value > maxHeight:
      self.ui.heightWidget.value = maxHeight

    # if the height changed, validate that the weight is in correct range.
    self.onHeightChange()

    return
  
  def onHeightChange(self) -> None:
    # if height changes, this changes the weight range.
    # validate that the weight is now within the supported range and clamp if required.
    height = self.ui.heightWidget.value
    trimester = self.ui.trimesterWidget.value
    head = self.ui.headDownCheckBox.checked
    minWeight, maxWeight = GetWeightRangeFromLookupTable(trimester, head, height)
    self.ui.weightWidget.minimum = minWeight
    self.ui.weightWidget.maximum = maxWeight
    if self.ui.weightWidget.value < minWeight:
      self.ui.weightWidget.value = minWeight
    if self.ui.weightWidget.value > maxWeight:
      self.ui.weightWidget.value = maxWeight

    return

  def onApplyButton(self) -> None:
    """Run processing when user clicks "Apply" button."""
    with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
      # Compute output
      trimester = self.ui.trimesterWidget.value
      head = self.ui.headDownCheckBox.checked
      height = self.ui.heightWidget.value
      weight = self.ui.weightWidget.value
      voxelSize = []
      voxelSize.append(self.ui.voxelSizeSaggitalWidget.value)
      voxelSize.append(self.ui.voxelSizeCoronalWidget.value)
      voxelSize.append(self.ui.voxelSizeAxialWidget.value)

      doPolyDataSegmentation = self.ui.generatePolyDataSegmentationCheckBox.checked
      doVolumeSegmentation = self.ui.generateVolumeSegmentationCheckBox.checked
      exportVoxelized = self.ui.exportVoxelizedCheckBox.checked
      exportVoxelizedDir = self.ui.exportVoxelizedDirectory.directory
      self.logic.process(trimester, head, height, weight, voxelSize, doPolyDataSegmentation, doVolumeSegmentation, exportVoxelized, exportVoxelizedDir)

  def onExportVoxelizedChange(self) -> None:
    exportVoxelizedEnabled = self.ui.exportVoxelizedCheckBox.checked
    print(exportVoxelizedEnabled)
    self.ui.exportVoxelizedDirectory.enabled = exportVoxelizedEnabled
  

class CreateFantomModuleLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self) -> None:
    """Called when the logic class is instantiated. Can be used for initializing member variables."""
    ScriptedLoadableModuleLogic.__init__(self)

  def getParameterNode(self):
    return CreateFantomModuleParameterNode(super().getParameterNode())
    
  def createVolumeNode(self, voxelSize):
    volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    volumeNode.SetName("Volume")
    volumeNode.CreateDefaultDisplayNodes()
    volumeNode.CreateDefaultStorageNode()
    volumeNode.SetSpacing(voxelSize)
    volumeNode.SetIJKToRASDirections([[1,0,0], [0,1,0], [0,0,1]])
    return volumeNode

  def createVolumeSegmentationNode(self):
    segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    segmentationNode.SetName("Volume Segmentation")
    segmentationNode.CreateDefaultDisplayNodes()
    segmentationNode.SetSourceRepresentationToBinaryLabelmap()
    return segmentationNode
  
  def createClosedSurfaceSegmentationNode(self):
    segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    segmentationNode.SetName("PolyData Segmentation")
    segmentationNode.CreateDefaultDisplayNodes()
    segmentationNode.SetSourceRepresentationToClosedSurface()
    return segmentationNode
  
  def getLookupArray(self, trimester, head):
    jsonPath = os.path.dirname(os.path.abspath(__file__))
    jsonPath = jsonPath + "/Resources/Data/_lookup_table.json"
    with open(jsonPath) as jsonFile:
      jsonData = json.load(jsonFile)
      return jsonData
    return None

  def readVtkPolyObjectFromGltf(self, gltfPath):
    reader = vtk.vtkGLTFReader() 
    reader.SetFileName(gltfPath)
    reader.Update()
    vtkPolyObject = reader.GetOutput().NewIterator().GetCurrentDataObject()
    return vtkPolyObject

  def getScaledVtkPolyObjectWithWeights(self, name, trimester, head, heightBlendFactor, weightBlendFactor):
    # prepare directory path where glb files are stored.
    # if file does not exist (can happen because some trimesters dont have some files) return None. handled later.
    gltfDir = os.path.dirname(os.path.abspath(__file__)) + "/Resources/Data/" + getTrimesterHeadString(trimester, head)
    if not os.path.isfile(gltfDir + "/fantom_base/" + name + ".glb"):
      return None
    
    # load base vtk poly object.
    objBase = self.readVtkPolyObjectFromGltf(gltfDir + "/fantom_base/" + name + ".glb")
    objBasePoints = objBase.GetPoints()

    # load blend shape for height blending
    if heightBlendFactor > 0:
      objHeightShape = self.readVtkPolyObjectFromGltf(gltfDir + "/fantom_scaled_up/" + name + ".glb")
    else:
      objHeightShape = self.readVtkPolyObjectFromGltf(gltfDir + "/fantom_scaled_down/" + name + ".glb")
    heightBlendFactor = abs(heightBlendFactor)

    # get points
    objHeightPoints = objHeightShape.GetPoints()
    
    # iterate over points and blend
    for i in range(objBasePoints.GetNumberOfPoints()):
      pointBase = objBasePoints.GetPoint(i)
      pointHeight = objHeightPoints.GetPoint(i)
      x = pointBase[0] + heightBlendFactor * (pointHeight[0] - pointBase[0])
      y = pointBase[1] + heightBlendFactor * (pointHeight[1] - pointBase[1])
      z = pointBase[2] + heightBlendFactor * (pointHeight[2] - pointBase[2])
      objBasePoints.SetPoint(i, x, y, z)

    # modify points (height) and get the bounding box to clamp after applying soft tissue scaling
    objBasePoints.Modified()
    objBase.Modified()
    objBase.ComputeBounds()
    
    # if processing soft tissues, weight blending can be applied
    # otherwise return the current state
    if name != "soft_tissues":
      return objBase
    
    # load blend shape for height blending
    if weightBlendFactor > 0:
      objWeightShape = self.readVtkPolyObjectFromGltf(gltfDir + "/fantom_weight_up/soft_tissues.glb")
    else:
      objWeightShape = self.readVtkPolyObjectFromGltf(gltfDir + "/fantom_weight_down/soft_tissues.glb")
    weightBlendFactor = abs(weightBlendFactor)

    # load original base shape again.
    objSrc = self.readVtkPolyObjectFromGltf(gltfDir + "/fantom_base/soft_tissues.glb")
    objSrcPoints = objSrc.GetPoints()

    # get points
    objWeightPoints = objWeightShape.GetPoints()

    # get bounding box of scaled points in order to clamp on Z axis.
    objBasePoints = objBase.GetPoints()
    bounds = objBase.GetBounds() # (xmin, xmax, ymin, ymax, zmin, zmax), in mm

    # iterate over points and blend
    for i in range(objBasePoints.GetNumberOfPoints()):
      pointBase = objBasePoints.GetPoint(i)
      pointWeight = objWeightPoints.GetPoint(i)
      pointSrc = objSrcPoints.GetPoint(i)
      x = pointBase[0] + weightBlendFactor * (pointWeight[0] - pointSrc[0])
      y = pointBase[1] + weightBlendFactor * (pointWeight[1] - pointSrc[1])
      z = ClampValue(pointBase[2] + weightBlendFactor * (pointWeight[2] - pointSrc[2]), bounds[4], bounds[5]) # clamp Z
      objBasePoints.SetPoint(i, x, y, z)

    # finish point modification and return the object
    objBasePoints.Modified()
    objBase.Modified()
    objBase.ComputeBounds()
    return objBase

  def computeBlendFactors(self, trimester, head, height, weight):
    lookupTable = GetMorphLookupTable(trimester, head)
    
    heightBlendFactor = 0
    weightBlendFactor = 0

    for i in range (0, len(lookupTable) - 1):
      currentVal = lookupTable[i]
      nextVal = lookupTable[i + 1]
      # first, search for the two values that define the range of heights to which the current height belongs to
      # interpolate the factor for height scaling linearly. 
      if currentVal["height"] <= height and nextVal["height"] >= height:
        fac = (height - currentVal["height"]) / (nextVal["height"] - currentVal["height"])
        heightBlendFactor = currentVal["height_blend_factor"] + fac * (nextVal["height_blend_factor"] - currentVal["height_blend_factor"])
        # interpolate all factors for weight scaling also linearly.
        interpolatedWeights = []
        for j in range(0, len(currentVal["weights"])):
          interpW = currentVal["weights"][j] + fac * (nextVal["weights"][j] - currentVal["weights"][j])
          interpolatedWeights.append(interpW)
        # find the weight that fits.
        for j in range(0, len(interpolatedWeights) - 1):
          if interpolatedWeights[j] <= weight and interpolatedWeights[j + 1] >= weight:
            weightFac = (weight - interpolatedWeights[j]) / (interpolatedWeights[j + 1] - interpolatedWeights[j])
            currentWeightFac = currentVal["weight_blend_factors"][j]
            nextWeightFac = currentVal["weight_blend_factors"][j + 1]
            weightBlendFactor = currentWeightFac + weightFac * (nextWeightFac - currentWeightFac)
            return (heightBlendFactor, weightBlendFactor)
    
    return(heightBlendFactor, weightBlendFactor)

  def getScaledVtkPolyObject(self, name, trimester, head, height, weight):
    heightFactor, weightFactor = self.computeBlendFactors(trimester, head, height, weight)
    return self.getScaledVtkPolyObjectWithWeights(name, trimester, head, heightFactor, weightFactor)

  def initializeVolumeDataAndVolumeNode(self, volumeNode, volumeData, vtkPolyObject, voxelSize):
    volumeBounds = vtkPolyObject.GetBounds() # (xmin, xmax, ymin, ymax, zmin, zmax), in mm

    # Compute the bounds of the image (mm), extent (voxels) and volume origin.
    volumeDimensions = []
    volumeOrigin = []
    for axis in range(0, 3):
      valMin = volumeBounds[2 * axis]
      valMax = volumeBounds[2 * axis + 1]
      size = voxelSize[axis]
      volumeDimensions.append(math.ceil((valMax - valMin) / size) + 4) # include small padding
      volumeOrigin.append(valMin)
    
    # Allocate image data and fill with background value (-1000 for air)
    volumeData.SetDimensions(volumeDimensions)
    volumeData.AllocateScalars(vtk.VTK_INT, 1)
    volumeData.GetPointData().GetScalars().Fill(-1000)

    # Set up the volume node
    volumeNode.SetOrigin(volumeOrigin)
    volumeNode.SetAndObserveImageData(volumeData)
  
    return

  def applyPolyDataStencilToVolume(self, vtkPolyObject, volumeNode, volumeData, voxelSize, backgroundValue):
    polyDataToImageStencil = vtk.vtkPolyDataToImageStencil()
    polyDataToImageStencil.SetInputData(vtkPolyObject)
    polyDataToImageStencil.SetOutputOrigin(volumeNode.GetOrigin())
    polyDataToImageStencil.SetOutputSpacing(voxelSize)
    polyDataToImageStencil.SetOutputWholeExtent(volumeData.GetExtent())
    polyDataToImageStencil.Update()
    imageStencilData = polyDataToImageStencil.GetOutput()

    imageStencil = vtk.vtkImageStencil()
    imageStencil.SetStencilData(imageStencilData)
    imageStencil.ReverseStencilOn()
    imageStencil.SetBackgroundValue(backgroundValue)
    imageStencil.SetInputData(volumeData)
    imageStencil.SetOutput(volumeData)
    imageStencil.Update()
    
    return
  
  def createVolumeSegmentationNode(self):
    segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    segmentationNode.SetName("Segmentation")
    segmentationNode.CreateDefaultDisplayNodes()
    segmentationNode.SetSourceRepresentationToBinaryLabelmap()
    return segmentationNode

  def thresholdImage(self, volumeData, value):
    imageToImageStencil = vtk.vtkImageToImageStencil()
    imageToImageStencil.SetInputData(volumeData)
    imageToImageStencil.ThresholdBetween(value, value)
    imageToImageStencil.Update()

    return imageToImageStencil.GetOutput()  

  def replaceDataUsingStencil(self, volumeData, imageStencilData, newValue):
    imageStencil = vtk.vtkImageStencil()
    imageStencil.SetStencilData(imageStencilData)
    imageStencil.ReverseStencilOn()
    imageStencil.SetBackgroundValue(newValue)
    imageStencil.SetInputData(volumeData)
    imageStencil.SetOutput(volumeData)
    imageStencil.Update()

    return

  def process(self, trimester, head, height, weight, voxelSize, doPolySegmentation, doVolumeSegmentation, exportVoxel, exportVoxelDir) -> None:
    # Create a new volume node to display the generated CT image.
    volumeNode = self.createVolumeNode(voxelSize)
    # Create volume data to be used inside the volume node.
    volumeData = vtk.vtkImageData()

    # create polygon segmentation node if required..
    if doPolySegmentation:
      segmentationPolyDataNode = self.createClosedSurfaceSegmentationNode()
    else:
      segmentationPolyDataNode = None

    # Fetch the lookup array that defines the loading order of objects and hu values.
    lookupArray = self.getLookupArray(trimester, head)

    # create a progress dialog because the execution can take a while...
    progressDialog = slicer.util.createProgressDialog(parent = None, value = 0, maximum = 2 * len(lookupArray))

    # iterate over the lookup Array, create volume masks from poly data and build the volume with correct index assigned
    for lookupIndex in range(len(lookupArray)):
      lookupEntry = lookupArray[lookupIndex]
      
      # set progress dialog value
      progressDialog.setValue(lookupIndex)
      progressDialog.setLabelText("Step 1/2. Processing " + lookupEntry["id"])
      slicer.app.processEvents()

      # read the gltf file. It will have correct scaling and blend shape applied
      # if the file does not exist, that is ok because not all trimesters have all files.
      vtkPolyObject = self.getScaledVtkPolyObject(lookupEntry["id"], trimester, head, height, weight)
      if vtkPolyObject is None:
        continue
      
      # if this is the first entry, initialize the image
      # the first entry is the soft tissue segmentation and that one is the largest and defines the extent of the image
      if lookupIndex == 0:
        self.initializeVolumeDataAndVolumeNode(volumeNode, volumeData, vtkPolyObject, voxelSize)
        print("Requested height: " + str(height) + ". Requested weight: " + str(weight))
        massProperties = vtk.vtkMassProperties()
        massProperties.SetInputData(vtkPolyObject)
        massProperties.Update()
        outputVolumeMassEst = massProperties.GetVolume() * 0.001 * 0.001 * 0.97
        outputH = (vtkPolyObject.GetBounds()[5] - vtkPolyObject.GetBounds()[4]) * 0.1
        print("Generated height: " + str(outputH) + ". Generated weight(estimate): " + str(outputVolumeMassEst))
        
      # convert the poly data to voxels, using poly data as image stencil
      # we use a 10000 offset to avoid the index overlapping with some HU value.
      self.applyPolyDataStencilToVolume(vtkPolyObject, volumeNode, volumeData, voxelSize, 10000 + lookupIndex)  

      if doPolySegmentation:
        segmentationPolyDataNode.AddSegmentFromClosedSurfaceRepresentation(vtkPolyObject, lookupEntry["id"])

    # if enabled, export to voxelized format
    if exportVoxel:
      self.exportVoxelized(exportVoxelDir, lookupArray, 10000, volumeData, voxelSize, progressDialog)

    # create a volume segmentation node. 
    if doVolumeSegmentation:
      segmentationVolumeNode = self.createVolumeSegmentationNode()
    else:
      segmentationVolumeNode = None
    
    for lookupIndex in range(len(lookupArray)):
      lookupEntry = lookupArray[lookupIndex]

      # set progress dialog value
      progressDialog.setValue(len(lookupArray) + lookupIndex)
      progressDialog.setLabelText("Step 3/3. Processing " + lookupEntry["id"])
      slicer.app.processEvents()

      # this is the current value in volume node, offset by 10000 to avoid overlap between index and hu value.
      valueInVolumeNode = 10000 + lookupIndex

      # compute the hu value as just the average of min/max
      currentHUValue = 0.5 * (lookupEntry["hu_min"] + lookupEntry["hu_max"])

      # create the image stencil by thresholding the volume data with the current value in volume node.
      imageStencilData = self.thresholdImage(volumeData, valueInVolumeNode)
      
      # apply the image stencil to the volume data, in order to set the final, correct HU value.
      self.replaceDataUsingStencil(volumeData, imageStencilData, currentHUValue)

      if doVolumeSegmentation:
        # add binary label map to segmentation and fill it using the stencil
        binaryLabelMap = slicer.vtkOrientedImageData()
        dimensions = volumeData.GetDimensions()
        binaryLabelMap.SetDimensions(dimensions)
        binaryLabelMap.AllocateScalars(vtk.VTK_SHORT, 1)
        binaryLabelMap.GetPointData().GetScalars().Fill(0)
        self.replaceDataUsingStencil(binaryLabelMap, imageStencilData, 1)
        
        # set correct origin and set segmentation labelmap
        binaryLabelMap.SetOrigin(volumeNode.GetOrigin())
        segmentationVolumeNode.AddSegmentFromBinaryLabelmapRepresentation(binaryLabelMap, lookupEntry["id"])

    # close the progress dialog
    progressDialog.close()
    
    # finished
    return

  def exportVoxelized(self, exportDir, lookupArray, lookupOffset, volumeData, voxelSize, progressDialog):
    # find first available file name in the directory do avoid overwriting existing files 
    fileIndex = 0
    filepath = ""
    while True:
      filepath = os.path.join(exportDir, "voxelized_form_" + str(fileIndex))
      if not os.path.exists(filepath):
        break
      fileIndex = fileIndex + 1
    
    # open file for writing and export
    with open(filepath, "w") as file:
      # first write the volume data. 
      voxelIndex = 0
      dimensions = volumeData.GetDimensions()
      # TODO: (Luka) verify that this order of xyz for export is correct. 
      # If data is jumbled this should be the first place to look
      for x in range(dimensions[0]):
        progressDialog.setLabelText("Step 2/3. exporting slice " + str(x) + " out of " + str(dimensions[0]))
        slicer.app.processEvents()
        for y in range(dimensions[1]):
          for z in range(dimensions[2]):
            # writing 20 voxels per line
            # if first voxel in the line, pad with 4 spaces at the beginning of the line
            if voxelIndex % 20 == 0:
              file.write("    ")
            # get the voxel segmentation id and write it justified to 3 characters.
            # air will have idvalue of 0
            # the rest has idvalue offset by 1 compared to lookup table.
            idxInLookupArray = int(volumeData.GetScalarComponentAsFloat(x,y,z,0)) - lookupOffset
            if idxInLookupArray == -11000:
              idValue = 0
            else:
              idValue = lookupArray[idxInLookupArray]["export_id"] + 1 
            file.write(str(idValue).rjust(3))
            # if last voxel in line, newline
            if voxelIndex % 20 == 19:
              file.write("\r\n")
            # increment voxel index
            voxelIndex = voxelIndex + 1
      # final new line after last voxel if it was not exactly last voxel in the line
      if voxelIndex % 20 != 0:
        file.write("\r\n")  
      # write some new lines
      file.write("\r\n")
      file.write("\r\n")
      # write the lookup array. 
      # TODO: (Luka) does it have to be sorted by export_id?
      file.write("  0        $  air_outside\r\n")
      for item in lookupArray:
        file.write("  " + str(item["export_id"] + 1).ljust(9) + "$  " + item["id"] + "\r\n")
      # write some new lines
      file.write("\r\n")
      # write number of voxels
      file.write(f"number of voxels: 0:{dimensions[0]} 0:{dimensions[1]} 0:{dimensions[2]}\r\n")
      # write voxel size
      file.write(f"voxel size {voxelSize[0]:.3f} x {voxelSize[1]:.3f} x {voxelSize[2]:.3f}\r\n")
      # newline eof
      file.write("\r\n")
    
    # export done, log a mesage
    print("Exported voxelized form to " + filepath)

