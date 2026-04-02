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
import scipy
import numpy

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

def getLookupArray():
  jsonPath = os.path.dirname(os.path.abspath(__file__))
  jsonPath = jsonPath + "/Resources/Data/_lookup_table.json"
  with open(jsonPath) as jsonFile:
    jsonData = json.load(jsonFile)
    return jsonData
  return None

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


class GenerateFantomTabWidget:
  def __init__(self, logic, resourcePath):
    self.logic = logic
    self.resourcePath = resourcePath
    self.widget = slicer.util.loadUI(self.resourcePath('UI/GenerateFantomTab.ui'))
    self.ui = slicer.util.childWidgetVariables(self.widget)

    # Buttons
    self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
    self.ui.heightWidget.connect("valueChanged(double)", self.onHeightChange)
    self.ui.trimesterWidget.connect("valueChanged(double)", self.onTrimesterOrHeadChange)
    self.ui.headDownCheckBox.connect("stateChanged(int)", self.onTrimesterOrHeadChange)
    self.ui.exportVoxelizedCheckBox.connect("stateChanged(int)", self.onExportVoxelizedOrDicomChange)
    self.ui.exportDicomCheckBox.connect("stateChanged(int)", self.onExportVoxelizedOrDicomChange)
    self.ui.generateVolumeDataCheckBox.connect("stateChanged(int)", self.onGenerateVolumeDataChange)
    self.ui.generatePolyDataSegmentationCheckBox.connect("stateChanged(int)", self.applyButtonEnabling)
    self.ui.generateVolumeSegmentationCheckBox.connect("stateChanged(int)", self.applyButtonEnabling)
    self.ui.segmentationListWidget.connect("itemSelectionChanged()", self.applyButtonEnabling)
    self.ui.segmentationListComboBox.connect("currentIndexChanged(int)", self.segementationComboIndexChange)

    # make sure that the values are in a valid range
    self.onTrimesterOrHeadChange()

    # make sure that the folder selector is correctly enabled/disabled
    self.onExportVoxelizedOrDicomChange()

    # build segmentation list. 
    lookupArray = getLookupArray()
    for lookupEntry in lookupArray:
      id = lookupEntry["id"]
      self.ui.segmentationListWidget.addItem(id)

    # default selection for segmentation list
    self.initSegmentationPresetComboBox()
    defaultId = self.ui.segmentationListComboBox.findText("Default")
    self.ui.segmentationListComboBox.setCurrentIndex(defaultId)
    self.setSelectedSegmentationsFromPreset("Default")

    # make sure that the apply button has correct enabling state on init
    self.applyButtonEnabling() 

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

    # enable head down checkbox only in second trimester.
    if trimester == 2:
      self.ui.headDownCheckBox.setEnabled(True)
    else:
      self.ui.headDownCheckBox.setDisabled(True)

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
      exportDicom = self.ui.exportDicomCheckBox.checked
      exportVoxelizedDir = self.ui.exportVoxelizedDirectory.directory
      volumeEnabled = self.ui.generateVolumeDataCheckBox.checked
      selectedSegmentations = []
      for item in self.ui.segmentationListWidget.selectedItems():
        selectedSegmentations.append(item.text())
      self.logic.process(trimester, head, height, weight, voxelSize, selectedSegmentations, volumeEnabled, doPolyDataSegmentation, doVolumeSegmentation, exportVoxelized, exportDicom, exportVoxelizedDir)

  def onExportVoxelizedOrDicomChange(self) -> None:
    volumeEnabled = self.ui.generateVolumeDataCheckBox.checked
    exportVoxelizedEnabled = self.ui.exportVoxelizedCheckBox.checked
    exportDicomEnabled = self.ui.exportDicomCheckBox.checked
    self.ui.exportVoxelizedDirectory.enabled = (exportVoxelizedEnabled or exportDicomEnabled) and volumeEnabled

  def onGenerateVolumeDataChange(self) -> None:
    # when we disable generating volume data, disable the checkboxes for voxelized and dicom export.
    if self.ui.generateVolumeDataCheckBox.checked:
      self.ui.exportVoxelizedCheckBox.setEnabled(True)
      self.ui.exportDicomCheckBox.setEnabled(True)
    else:
      self.ui.exportVoxelizedCheckBox.setDisabled(True)
      self.ui.exportDicomCheckBox.setDisabled(True)
    self.onExportVoxelizedOrDicomChange()
    self.applyButtonEnabling()

  def applyButtonEnabling(self) -> None:
    hasSelected = len(self.ui.segmentationListWidget.selectedItems()) > 0
    volumeEnabled = self.ui.generateVolumeDataCheckBox.checked
    segmentationEnabled = self.ui.generatePolyDataSegmentationCheckBox.checked or self.ui.generateVolumeSegmentationCheckBox.checked
    applyEnabled = hasSelected and (volumeEnabled or segmentationEnabled)
    if applyEnabled:
      self.ui.applyButton.setEnabled(True)
    else:
      self.ui.applyButton.setDisabled(True)

  def setSelectedSegmentationsFromPreset(self, presetName) -> None:
    jsonPath = os.path.dirname(os.path.abspath(__file__))
    jsonPath = jsonPath + "/Resources/Data/SegmentationPresets/" + presetName + ".json"
    with open(jsonPath) as jsonFile:
      selectedSegmentations = json.load(jsonFile)
      for index in range(self.ui.segmentationListWidget.count):
        item = self.ui.segmentationListWidget.item(index)
        item.setSelected(item.text() in selectedSegmentations)

  def initSegmentationPresetComboBox(self) -> None:
    combobox = self.ui.segmentationListComboBox
    presetsDir = os.path.dirname(os.path.abspath(__file__))
    presetsDir += "/Resources/Data/SegmentationPresets"
    for item in os.listdir(presetsDir):
      if item.endswith(".json"):
        combobox.addItem(item[:-5])

  def segementationComboIndexChange(self, index) -> None:
    text = self.ui.segmentationListComboBox.itemText(index)
    self.setSelectedSegmentationsFromPreset(text)


class SegmentationToFantomTabWidget:
  def __init__(self, logic, resourcePath):
    self.logic = logic
    self.resourcePath = resourcePath
    self.widget = slicer.util.loadUI(self.resourcePath('UI/SegmentationToFantomTab.ui'))
    self.ui = slicer.util.childWidgetVariables(self.widget)

    # Buttons
    self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
    self.ui.exportVoxelizedCheckBox.connect("stateChanged(int)", self.onExportVoxelizedOrDicomChange)
    self.ui.exportDicomCheckBox.connect("stateChanged(int)", self.onExportVoxelizedOrDicomChange)
    self.ui.generateVolumeDataCheckBox.connect("stateChanged(int)", self.onGenerateVolumeDataChange)
    self.ui.segmentationNodeComboBox.setMRMLScene(slicer.mrmlScene)
    self.ui.segmentationNodeComboBox.connect("currentNodeChanged(bool)", self.onSegmentationNodeComboBoxChange)

    # make sure that the folder selector is correctly enabled/disabled
    self.onExportVoxelizedOrDicomChange()

    # make sure that the apply button has correct enabling state on init
    self.applyButtonEnabling() 

  def onApplyButton(self) -> None:
    """Run processing when user clicks "Apply" button."""
    with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
      # Compute output
      exportVoxelized = self.ui.exportVoxelizedCheckBox.checked
      exportDicom = self.ui.exportDicomCheckBox.checked
      exportVoxelizedDir = self.ui.exportVoxelizedDirectory.directory
      currentNodeID = self.ui.segmentationNodeComboBox.currentNodeID
      currentNode = slicer.mrmlScene.GetNodeByID(currentNodeID)
      segmentation = currentNode.GetSegmentation()

      self.logic.processFromSegmentation(segmentation, exportVoxelized, exportDicom, exportVoxelizedDir) 

  def onExportVoxelizedOrDicomChange(self) -> None:
    volumeEnabled = self.ui.generateVolumeDataCheckBox.checked
    exportVoxelizedEnabled = self.ui.exportVoxelizedCheckBox.checked
    exportDicomEnabled = self.ui.exportDicomCheckBox.checked
    self.ui.exportVoxelizedDirectory.enabled = (exportVoxelizedEnabled or exportDicomEnabled) and volumeEnabled

  def onGenerateVolumeDataChange(self) -> None:
    # when we disable generating volume data, disable the checkboxes for voxelized and dicom export.
    if self.ui.generateVolumeDataCheckBox.checked:
      self.ui.exportVoxelizedCheckBox.setEnabled(True)
      self.ui.exportDicomCheckBox.setEnabled(True)
    else:
      self.ui.exportVoxelizedCheckBox.setDisabled(True)
      self.ui.exportDicomCheckBox.setDisabled(True)
    self.onExportVoxelizedOrDicomChange()
    self.applyButtonEnabling()

  def onSegmentationNodeComboBoxChange(self, isValidNode) -> None:
    self.applyButtonEnabling()
  
  def applyButtonEnabling(self) -> None:
    applyEnabled = self.ui.generateVolumeDataCheckBox.checked
    currentNode = self.ui.segmentationNodeComboBox.currentNodeID
    if applyEnabled and currentNode:
      self.ui.applyButton.setEnabled(True)
    else:
      self.ui.applyButton.setDisabled(True)


class BlendTabWidget:
  def __init__(self, logic, resourcePath):
    self.logic = logic
    self.resourcePath = resourcePath
    self.widget = slicer.util.loadUI(self.resourcePath('UI/BlendSegmentationsTab.ui'))
    self.ui = slicer.util.childWidgetVariables(self.widget)

    # Buttons
    self.ui.generateMarkupLinesButton.connect("clicked(bool)", self.onGenerateMarkupLinesButton)
    self.ui.alignButton.connect("clicked(bool)", self.onAlignButton)
    self.ui.blendButton.connect("clicked(bool)", self.onBlendButton)
    self.ui.alignNodeComboBox.setMRMLScene(slicer.mrmlScene)
    self.ui.blendNode1ComboBox.setMRMLScene(slicer.mrmlScene)
    self.ui.blendNode2ComboBox.setMRMLScene(slicer.mrmlScene)

  def onGenerateMarkupLinesButton(self) -> None:
    self.logic.setUpMarkupLines()

  def onAlignButton(self) -> None:
    alignRotation = self.ui.alignRotationCheckBox.checked
    alignTranslation = self.ui.alignTranslationCheckBox.checked
    nodeToAlignID = self.ui.alignNodeComboBox.currentNodeID
    nodeToAlign = slicer.mrmlScene.GetNodeByID(nodeToAlignID)
    somethingToAlign = alignTranslation or alignRotation
    if not (somethingToAlign or nodeToAlign):
      return
    self.logic.alignNodeUsingMarkupLines(nodeToAlign, alignRotation, alignTranslation)

  def onBlendButton(self) -> None:
    nodeID1 = self.ui.blendNode1ComboBox.currentNodeID
    nodeID2 = self.ui.blendNode2ComboBox.currentNodeID
    node1 = slicer.mrmlScene.GetNodeByID(nodeID1)
    node2 = slicer.mrmlScene.GetNodeByID(nodeID2)
    if not (node1 and node2):
      return
    self.logic.blendSegmentationNodes(node1, node2)

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

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

    # Create tab widgets, inject into tabs
    self.generateFantomTabUI = GenerateFantomTabWidget(self.logic, self.resourcePath)
    self.blendSegmentationsTabUI = BlendTabWidget(self.logic, self.resourcePath)
    self.segmentToFantomTabUI = SegmentationToFantomTabWidget(self.logic, self.resourcePath)
    self.ui.generateFantomTab.layout().addWidget(self.generateFantomTabUI.widget)
    self.ui.blendSegmentationsTab.layout().addWidget(self.blendSegmentationsTabUI.widget)
    self.ui.segmentToFantomTab.layout().addWidget(self.segmentToFantomTabUI.widget)

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

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

  def initializeVolumeDataAndVolumeNode(self, volumeNode, volumeData, volumeBounds, voxelSize):
    # Compute the bounds of the image (mm), extent (voxels) and volume origin.
    volumeDimensions = []
    volumeOrigin = []
    for axis in range(0, 3):
      valMin = volumeBounds[2 * axis]
      valMax = volumeBounds[2 * axis + 1]
      size = voxelSize[axis]
      volumeDimensions.append(math.ceil((valMax - valMin) / size))
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
  
  def applyImageStencilToVolume(self, imageData, volumeData, backgroundValue):
    imageDataToImageStencil = vtk.vtkImageToImageStencil()
    imageDataToImageStencil.SetInputData(imageData)
    imageDataToImageStencil.ThresholdByUpper(1)
    imageDataToImageStencil.Update()
    imageStencilData = imageDataToImageStencil.GetOutput()

    imageStencil = vtk.vtkImageStencil()
    imageStencil.SetStencilData(imageStencilData)
    imageStencil.ReverseStencilOn()
    imageStencil.SetBackgroundValue(backgroundValue)
    imageStencil.SetInputData(volumeData)
    imageStencil.SetOutput(volumeData)
    imageStencil.Update()
    
  
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

  def process(self, trimester, head, height, weight, voxelSize, selectedSegmentationIds, createVolumeData, doPolySegmentation, doVolumeSegmentation, exportVoxel, exportDicom, exportVoxelDir) -> None:
    if not createVolumeData:
      exportVoxel = False
      exportDicom = False

    if len(selectedSegmentationIds) < 0:
      return
    
    # note that, even if we don't generate the volume node itself, it is still necessary to generate the masks for segmentations
    # in order for the volume data segmentation to be generated. 

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
    lookupArray = getLookupArray()

    # create a progress dialog because the execution can take a while...
    progressDialog = slicer.util.createProgressDialog(parent = None, value = 0, maximum = 2 * len(lookupArray))

    # iterate over the lookup Array, create volume masks from poly data and build the volume with correct index assigned
    for lookupIndex in range(len(lookupArray)):
      lookupEntry = lookupArray[lookupIndex]

      # only allow segmentation ids that are selected.
      if not lookupEntry["id"] in selectedSegmentationIds:
        continue 
      
      # set progress dialog value
      progressDialog.setValue(lookupIndex)
      progressDialog.setLabelText("Processing " + lookupEntry["id"])
      slicer.app.processEvents()

      # read the gltf file. It will have correct scaling and blend shape applied
      # if the file does not exist, that is ok because not all trimesters have all files.
      vtkPolyObject = self.getScaledVtkPolyObject(lookupEntry["id"], trimester, head, height, weight)
      if vtkPolyObject is None:
        continue
      
      # if this is the first entry, initialize the image
      # the first entry is the soft tissue segmentation and that one is the largest and defines the extent of the image
      if lookupIndex == 0:
        self.initializeVolumeDataAndVolumeNode(volumeNode, volumeData, vtkPolyObject.GetBounds(), voxelSize)
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

    fileIndex = 0
    if exportDicom or exportVoxel:
      fileIndex = self.getFileIndex(exportVoxelDir)

    # if enabled, export to voxelized format
    if exportVoxel:
      self.exportVoxelized(exportVoxelDir, fileIndex, lookupArray, 10000, volumeData, voxelSize, progressDialog)

    # create a volume segmentation node. 
    if doVolumeSegmentation:
      segmentationVolumeNode = self.createVolumeSegmentationNode()
    else:
      segmentationVolumeNode = None
    
    for lookupIndex in range(len(lookupArray)):
      lookupEntry = lookupArray[lookupIndex]

      # only allow segmentation ids that are selected.
      if not lookupEntry["id"] in selectedSegmentationIds:
        continue 

      # set progress dialog value
      progressDialog.setValue(len(lookupArray) + lookupIndex)
      progressDialog.setLabelText("Processing " + lookupEntry["id"])
      slicer.app.processEvents()

      # this is the current value in volume node, offset by 10000 to avoid overlap between index and hu value.
      valueInVolumeNode = 10000 + lookupIndex

      # compute the hu value as just the average of min/max
      currentHUValue = 0.5 * (lookupEntry["hu_min"] + lookupEntry["hu_max"])

      # create the image stencil by thresholding the volume data with the current value in volume node.
      imageStencilData = self.thresholdImage(volumeData, valueInVolumeNode)
      
      # apply the image stencil to the volume data, in order to set the final, correct HU value.
      if createVolumeData:
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
        binaryLabelMap.SetSpacing(voxelSize)
        segmentationVolumeNode.AddSegmentFromBinaryLabelmapRepresentation(binaryLabelMap, lookupEntry["id"])

    # export dicom if enabled.
    if exportDicom:
      self.exportDicom(exportVoxelDir, fileIndex, volumeNode, progressDialog)

    # delete the volume node if it's not required
    if not createVolumeData:
      slicer.mrmlScene.RemoveNode(volumeNode)

    # close the progress dialog
    progressDialog.close()
    
    # finished
    return

  def getFileIndex(self, exportDir):
    # find first available file name in the directory do avoid overwriting existing files 
    fileIndex = 0
    filepath = ""
    while True:
      filepath = os.path.join(exportDir, "voxelized_form_" + str(fileIndex))
      dicompath = os.path.join(exportDir, "DICOM_" + str(fileIndex))
      if os.path.exists(filepath) or os.path.exists(dicompath):
        fileIndex = fileIndex + 1
      else:
        break
    return fileIndex

  def exportVoxelized(self, exportDir, fileIndex, lookupArray, lookupOffset, volumeData, voxelSize, progressDialog):
    filepath = os.path.join(exportDir, "voxelized_form_" + str(fileIndex))
    # open file for writing and export
    with open(filepath, "w") as file:
      # first write the volume data. 
      voxelIndex = 0
      dimensions = volumeData.GetDimensions()
      # TODO: (Luka) verify that this order of xyz for export is correct. 
      # If data is jumbled this should be the first place to look
      for z in range(dimensions[2]):
        progressDialog.setLabelText("Exporting slice " + str(z) + " out of " + str(dimensions[2]))
        slicer.app.processEvents()
        for y in range(dimensions[1]):
          for x in range(dimensions[0]):
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
      # write voxel size, * 0.1 to convert from mm to cm
      file.write(f"voxel size {(0.1 * voxelSize[0]):.3f} x {(0.1 * voxelSize[1]):.3f} x {(0.1 * voxelSize[2]):.3f}\r\n")
      # newline eof
      file.write("\r\n")
    
    # export done, log a mesage
    print("Exported voxelized form to " + filepath)

  def exportDicom(self, exportDir, fileIndex, volumeNode, progressDialog):
    # update progress dialog string
    progressDialog.setLabelText("Exporting Dicom...")
    
    # create the directory where dicom will be exported
    dicomDirPath = os.path.join(exportDir, "DICOM_" + str(fileIndex))
    os.mkdir(dicomDirPath)

    # create parameters and execute createdicomseries module
    parameters = {}
    parameters["inputVolume"] = volumeNode
    parameters["dicomDirectory"] = dicomDirPath
    dicomSeriesModule = slicer.modules.createdicomseries
    cliNode = slicer.cli.runSync(dicomSeriesModule, None, parameters)
    slicer.mrmlScene.RemoveNode(cliNode)

    return

  def processFromSegmentation(self, segmentation, exportVoxel, exportDicom, exportDir) -> None:
    # from the segmentation, build a map from segment name -> segment id. 
    segmentNameToIdMap = dict()
    for segmentId in segmentation.GetSegmentIDs():
      segment = segmentation.GetSegment(segmentId)
      segmentNameToIdMap[segment.GetName()] = segmentId

    # Fetch the lookup array that defines the loading order of objects and hu values.
    lookupArray = getLookupArray()

    # get the soft tissue imagedata. 
    # use the soft tissues segment as a reference volume.
    lableMapName = slicer.vtkSegmentationConverter.GetSegmentationBinaryLabelmapRepresentationName()
    softTissueImageData = segmentation.GetSegment(segmentNameToIdMap["soft_tissues"]).GetRepresentation(lableMapName)
    voxelSize = softTissueImageData.GetSpacing()
    bounds = softTissueImageData.GetBounds()

    # create a progress dialog because the execution can take a while...
    progressDialog = slicer.util.createProgressDialog(parent = None, value = 0, maximum = 2 * len(lookupArray))

    # create volume node and volume data
    # Create volume data to be used inside the volume node.
    volumeNode = self.createVolumeNode(voxelSize)
    volumeData = vtk.vtkImageData()
    self.initializeVolumeDataAndVolumeNode(volumeNode, volumeData, bounds, voxelSize)

    # iterate over the lookup Array, create volume masks from poly data and build the volume with correct index assigned
    for lookupIndex in range(len(lookupArray)):
      lookupEntry = lookupArray[lookupIndex]
      # only allow segmentation ids that are available are processed
      if not lookupEntry["id"] in segmentNameToIdMap:
        continue 
      # get segmentation.
      currentSegmentationVolumeData = segmentation.GetSegment(segmentNameToIdMap[lookupEntry["id"]]).GetRepresentation(lableMapName)
      if currentSegmentationVolumeData is None:
        continue

      # set progress dialog value
      progressDialog.setValue(lookupIndex)
      progressDialog.setLabelText("Processing " + lookupEntry["id"])
      slicer.app.processEvents()
                 
      # apply image as stencil
      self.applyImageStencilToVolume(currentSegmentationVolumeData, volumeData, 10000 + lookupIndex)

    fileIndex = 0
    if exportDicom or exportVoxel:
      fileIndex = self.getFileIndex(exportDir)

    # if enabled, export to voxelized format
    if exportVoxel:
      self.exportVoxelized(exportDir, fileIndex, lookupArray, 10000, volumeData, voxelSize, progressDialog)

    # make the volume with appropriate segmentation ids
    for lookupIndex in range(len(lookupArray)):
      lookupEntry = lookupArray[lookupIndex]

      # only allow segmentation ids that are selected.
      if not lookupEntry["id"] in segmentNameToIdMap:
        continue 

      # set progress dialog value
      progressDialog.setValue(len(lookupArray) + lookupIndex)
      progressDialog.setLabelText("Processing " + lookupEntry["id"])
      slicer.app.processEvents()

      # this is the current value in volume node, offset by 10000 to avoid overlap between index and hu value.
      valueInVolumeNode = 10000 + lookupIndex

      # compute the hu value as just the average of min/max
      currentHUValue = 0.5 * (lookupEntry["hu_min"] + lookupEntry["hu_max"])

      # create the image stencil by thresholding the volume data with the current value in volume node.
      imageStencilData = self.thresholdImage(volumeData, valueInVolumeNode)
      
      # apply the image stencil to the volume data, in order to set the final, correct HU value.
      self.replaceDataUsingStencil(volumeData, imageStencilData, currentHUValue)

    # export dicom if enabled.
    if exportDicom:
      self.exportDicom(exportDir, fileIndex, volumeNode, progressDialog)

    # close the progress dialog
    progressDialog.close()
    
    # finished
    return

  def setUpMarkupLines(self) -> None:
    for lineIdx in range(4):
      markupLineName = "FantomLine" + str(lineIdx)
      itemList = slicer.mrmlScene.GetNodesByName(markupLineName)
      if itemList.GetNumberOfItems() > 0:
        lineNode = itemList.GetItemAsObject(0)
      else:
        lineNode = slicer.modules.markups.logic().AddNewMarkupsNode("vtkMRMLMarkupsLineNode", markupLineName)
        lineNode.CreateDefaultDisplayNodes()
      # display settings
      displayNode = lineNode.GetDisplayNode()
      displayNode.SetGlyphTypeFromString("CrossDot2D")
      displayNode.SetPropertiesLabelVisibility(False)
      displayNode.SetPointLabelsVisibility(True)
      displayNode.SetOccludedVisibility(True)
      displayNode.SetSliceProjection(True)
      # set some reasonable default coordinates for line end points (RAS)
      coordR = 50 if lineIdx & 1 else -50
      coordA = 50 if lineIdx & 2 else -50
      lineNode.SetLineStartPosition((coordR, coordA, 100))
      lineNode.SetLineEndPosition((coordR, coordA, 0))
      # start, end point labels
      lineNode.SetNthControlPointLabel(0, str(lineIdx) + " Patient")
      lineNode.SetNthControlPointLabel(1, str(lineIdx) + " Fantom")
    # switch to markups module to edit the lines.
    slicer.util.selectModule("Markups")
  
  def alignNodeUsingMarkupLines(self, nodeToAlign, alignRotation, alignTranslation) -> None:
    # gather the markup lines and their start/end positions 
    startPositions = []
    endPositions = []
    lineNodes = []
    for lineIdx in range(4):
      markupLineName = "FantomLine" + str(lineIdx)
      itemList = slicer.mrmlScene.GetNodesByName(markupLineName)
      if itemList.GetNumberOfItems() < 1:
        print("item list empty")
        return
      lineNode = itemList.GetItemAsObject(0)
      startPositions.append(numpy.array(lineNode.GetLineStartPosition()))
      endPositions.append(numpy.array(lineNode.GetLineEndPosition()))
      lineNodes.append(lineNode)
    # kabsch algorithm to construct the transform matrix
    # compute the translation matrix part
    startMidPoint = startPositions[0]
    endMidPoint = endPositions[0]
    for idx in range(1, 4):
      startMidPoint = startMidPoint + startPositions[idx]
      endMidPoint = endMidPoint + endPositions[idx]
    startMidPoint = 0.25 * startMidPoint
    endMidPoint = 0.25 * endMidPoint
    # move points to origin
    # compute sum of lengths of each point-origin
    startLen = 0.0
    endLen = 0.0
    startPositionsOrigin = []
    endPositionsOrigin = []
    for idx in range(4):
      startPositionsOrigin.append(startPositions[idx] - startMidPoint)
      endPositionsOrigin.append(endPositions[idx] - endMidPoint)
      startLen = startLen + numpy.linalg.norm(startPositions[idx])
      endLen = endLen + numpy.linalg.norm(endPositions[idx])
    # scale. scale factor is computed by summing up the distances from point to origin. 
    scaleFac = endLen / startLen
    for idx in range(4):
      startPositionsOrigin[idx] = scaleFac * startPositions[idx]
    # kabsch algorithm to compute the rotation part
    alignRes = scipy.spatial.transform.Rotation.align_vectors(endPositionsOrigin, startPositionsOrigin)
    # final transformation matrix
    rotationMatrix = numpy.eye(4)
    rotationMatrix[:3, :3] = alignRes[0].as_matrix()
    srcPivot = numpy.array(startMidPoint)
    srcToOrigin = numpy.eye(4)
    srcToOrigin[:3,3] = -srcPivot
    dstPivot = numpy.array(endMidPoint)
    originToDst = numpy.eye(4)
    originToDst[:3,3] = dstPivot
    if alignRotation and alignTranslation:
      transform = originToDst @ rotationMatrix @ srcToOrigin
    elif alignRotation:
      transform = rotationMatrix
    elif alignTranslation:
      transform = originToDst @ srcToOrigin
    else:
      transform = numpy.eye(4)
    # apply transformation to markup line start points and set them back.
    for idx in range(4):
      posH = numpy.append(startPositions[idx], 1)
      posH = transform @ posH
      startPositions[idx] = posH[:3] / posH[3]
      lineNodes[idx].SetLineStartPosition(startPositions[idx])
    # apply transformation to segmentation node
    vtkTrans = vtk.vtkTransform()
    vtkMat = slicer.util.vtkMatrixFromArray(transform)
    vtkTrans.SetMatrix(vtkMat)
    nodeToAlign.ApplyTransform(vtkTrans)
    nodeToAlign.GetDisplayNode().Modified()
    return

  def blendSegmentationNodes(self, node1, node2) -> None:
    return
