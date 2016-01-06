/******************************************************************************
 * The MIT License (MIT)
 * 
 * Copyright (c) 2015 Baldur Karlsson
 * 
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * 
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 * 
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 ******************************************************************************/

#pragma once

// since we don't use these macros, we undefine them so they don't interfere
// with bool names etc
#undef VK_KHR_xlib_surface
#undef VK_KHR_xcb_surface
#undef VK_KHR_win32_surface
#undef VK_KHR_surface
#undef VK_KHR_swapchain

#if defined(VK_USE_PLATFORM_WIN32_KHR)

#define HookInitInstance_PlatformSpecific() \
	HookInitExtension(VK_KHR_win32_surface, CreateWin32SurfaceKHR); \
	HookInitExtension(VK_KHR_win32_surface, GetPhysicalDeviceWin32PresentationSupportKHR);

#define HookDefine_PlatformSpecific() \
	HookDefine5(VkResult, vkCreateWin32SurfaceKHR, VkInstance, instance, HINSTANCE, hinstance, HWND, hwnd, const VkAllocationCallbacks*, pAllocator, VkSurfaceKHR*, pSurface); \
	HookDefine2(VkBool32, vkGetPhysicalDeviceWin32PresentationSupportKHR, VkPhysicalDevice, physicalDevice, uint32_t, queueFamilyIndex); \

#elif defined(VK_USE_PLATFORM_XCB_KHR) || defined(VK_USE_PLATFORM_XLIB_KHR)

#if defined(VK_USE_PLATFORM_XCB_KHR)

#define HookInitInstance_PlatformSpecific_Xcb() \
	HookInitExtension(VK_KHR_xcb_surface, CreateXcbSurfaceKHR); \
	HookInitExtension(VK_KHR_xcb_surface, GetPhysicalDeviceXcbPresentationSupportKHR);

#define HookDefine_PlatformSpecific_Xcb() \
	HookDefine5(VkResult, vkCreateXcbSurfaceKHR, VkInstance, instance, xcb_connection_t*, connection, xcb_window_t, window, const VkAllocationCallbacks*, pAllocator, VkSurfaceKHR*, pSurface); \
	HookDefine4(VkBool32, vkGetPhysicalDeviceXcbPresentationSupportKHR, VkPhysicalDevice, physicalDevice, uint32_t, queueFamilyIndex, xcb_connection_t*, connection, xcb_visualid_t, visual_id); \

#else

#define HookInitInstance_PlatformSpecific_Xcb()
#define HookDefine_PlatformSpecific_Xcb()

#endif

#if defined(VK_USE_PLATFORM_XLIB_KHR)

#define HookInitInstance_PlatformSpecific_Xlib() \
	HookInitExtension(VK_KHR_xlib_surface, CreateXlibSurfaceKHR); \
	HookInitExtension(VK_KHR_xlib_surface, GetPhysicalDeviceXlibPresentationSupportKHR);

#define HookDefine_PlatformSpecific_Xlib() \
	HookDefine5(VkResult, vkCreateXlibSurfaceKHR, VkInstance, instance, Display*, dpy, Window, window, const VkAllocationCallbacks*, pAllocator, VkSurfaceKHR*, pSurface); \
	HookDefine4(VkBool32, vkGetPhysicalDeviceXlibPresentationSupportKHR, VkPhysicalDevice, physicalDevice, uint32_t, queueFamilyIndex, Display*, dpy, VisualID, visualID); \

#else

#define HookInitInstance_PlatformSpecific_Xlib()
#define HookDefine_PlatformSpecific_Xlib()

#endif

#define HookInitInstance_PlatformSpecific() HookInitInstance_PlatformSpecific_Xcb() HookInitInstance_PlatformSpecific_Xlib()
#define HookDefine_PlatformSpecific() HookDefine_PlatformSpecific_Xcb() HookDefine_PlatformSpecific_Xlib()

#endif

#define HookInitVulkanInstance() \
	HookInit(CreateInstance); \
	HookInit(DestroyInstance); \
	HookInit(EnumeratePhysicalDevices); \
	HookInit(GetPhysicalDeviceFeatures); \
	HookInit(GetPhysicalDeviceImageFormatProperties); \
	HookInit(GetPhysicalDeviceFormatProperties); \
	HookInit(GetPhysicalDeviceSparseImageFormatProperties); \
	HookInit(GetPhysicalDeviceProperties); \
	HookInit(GetPhysicalDeviceQueueFamilyProperties); \
	HookInit(GetPhysicalDeviceMemoryProperties);

#define HookInitVulkanDevice() \
	HookInit(CreateDevice); \
	HookInit(DestroyDevice); \
	HookInit(GetDeviceQueue); \
	HookInit(QueueSubmit); \
	HookInit(QueueWaitIdle); \
	HookInit(DeviceWaitIdle); \
	HookInit(AllocateMemory); \
	HookInit(FreeMemory); \
	HookInit(MapMemory); \
	HookInit(UnmapMemory); \
	HookInit(FlushMappedMemoryRanges); \
	HookInit(InvalidateMappedMemoryRanges); \
	HookInit(GetDeviceMemoryCommitment); \
	HookInit(BindBufferMemory); \
	HookInit(BindImageMemory); \
	HookInit(QueueBindSparse); \
	HookInit(CreateBuffer); \
	HookInit(DestroyBuffer); \
	HookInit(CreateBufferView); \
	HookInit(DestroyBufferView); \
	HookInit(CreateImage); \
	HookInit(DestroyImage); \
	HookInit(GetImageSubresourceLayout); \
	HookInit(GetBufferMemoryRequirements); \
	HookInit(GetImageMemoryRequirements); \
	HookInit(GetImageSparseMemoryRequirements); \
	HookInit(CreateImageView); \
	HookInit(DestroyImageView); \
	HookInit(CreateShaderModule); \
	HookInit(DestroyShaderModule); \
	HookInit(CreateGraphicsPipelines); \
	HookInit(CreateComputePipelines); \
	HookInit(DestroyPipeline); \
	HookInit(CreatePipelineCache); \
	HookInit(GetPipelineCacheData); \
	HookInit(MergePipelineCaches); \
	HookInit(DestroyPipelineCache); \
	HookInit(CreatePipelineLayout); \
	HookInit(DestroyPipelineLayout); \
	HookInit(CreateSemaphore); \
	HookInit(DestroySemaphore); \
	HookInit(CreateFence); \
	HookInit(GetFenceStatus); \
	HookInit(ResetFences); \
	HookInit(WaitForFences); \
	HookInit(DestroyFence); \
	HookInit(CreateEvent); \
	HookInit(GetEventStatus); \
	HookInit(ResetEvent); \
	HookInit(SetEvent); \
	HookInit(DestroyEvent); \
	HookInit(CreateQueryPool); \
	HookInit(GetQueryPoolResults); \
	HookInit(DestroyQueryPool); \
	HookInit(CreateSampler); \
	HookInit(DestroySampler); \
	HookInit(CreateDescriptorSetLayout); \
	HookInit(DestroyDescriptorSetLayout); \
	HookInit(CreateDescriptorPool); \
	HookInit(ResetDescriptorPool); \
	HookInit(DestroyDescriptorPool); \
	HookInit(AllocateDescriptorSets); \
	HookInit(UpdateDescriptorSets); \
	HookInit(FreeDescriptorSets); \
	HookInit(GetRenderAreaGranularity); \
	HookInit(CreateCommandPool); \
	HookInit(DestroyCommandPool); \
	HookInit(ResetCommandPool); \
	HookInit(AllocateCommandBuffers); \
	HookInit(FreeCommandBuffers); \
	HookInit(BeginCommandBuffer); \
	HookInit(EndCommandBuffer); \
	HookInit(ResetCommandBuffer); \
	HookInit(CmdBindPipeline); \
	HookInit(CmdSetViewport); \
	HookInit(CmdSetScissor); \
	HookInit(CmdSetLineWidth); \
	HookInit(CmdSetDepthBias); \
	HookInit(CmdSetBlendConstants); \
	HookInit(CmdSetDepthBounds); \
	HookInit(CmdSetStencilCompareMask); \
	HookInit(CmdSetStencilWriteMask); \
	HookInit(CmdSetStencilReference); \
	HookInit(CmdBindDescriptorSets); \
	HookInit(CmdBindVertexBuffers); \
	HookInit(CmdBindIndexBuffer); \
	HookInit(CmdDraw); \
	HookInit(CmdDrawIndirect); \
	HookInit(CmdDrawIndexed); \
	HookInit(CmdDrawIndexedIndirect); \
	HookInit(CmdDispatch); \
	HookInit(CmdDispatchIndirect); \
	HookInit(CmdCopyBufferToImage); \
	HookInit(CmdCopyImageToBuffer); \
	HookInit(CmdCopyBuffer); \
	HookInit(CmdCopyImage); \
	HookInit(CmdBlitImage); \
	HookInit(CmdResolveImage); \
	HookInit(CmdUpdateBuffer); \
	HookInit(CmdFillBuffer); \
	HookInit(CmdPushConstants); \
	HookInit(CmdClearColorImage); \
	HookInit(CmdClearDepthStencilImage); \
	HookInit(CmdClearAttachments); \
	HookInit(CmdPipelineBarrier); \
	HookInit(CmdWriteTimestamp); \
	HookInit(CmdCopyQueryPoolResults); \
	HookInit(CmdBeginQuery); \
	HookInit(CmdEndQuery); \
	HookInit(CmdResetQueryPool); \
	HookInit(CmdSetEvent); \
	HookInit(CmdResetEvent); \
	HookInit(CmdWaitEvents); \
	HookInit(CreateFramebuffer); \
	HookInit(DestroyFramebuffer); \
	HookInit(CreateRenderPass); \
	HookInit(DestroyRenderPass); \
	HookInit(CmdBeginRenderPass); \
	HookInit(CmdNextSubpass); \
	HookInit(CmdExecuteCommands); \
	HookInit(CmdEndRenderPass);

// for simplicity and since the check itself is platform agnostic,
// these aren't protected in platform defines
#define CheckInstanceExts() \
	CheckExt(VK_KHR_xlib_surface) \
	CheckExt(VK_KHR_xcb_surface) \
	CheckExt(VK_KHR_win32_surface) \
	CheckExt(VK_KHR_surface) \
	CheckExt(DEBUG_REPORT)

#define CheckDeviceExts() \
	CheckExt(VK_LUNARG_DEBUG_MARKER) \
	CheckExt(VK_KHR_swapchain)

#define HookInitVulkanInstanceExts() \
	HookInitExtension(VK_KHR_surface, DestroySurfaceKHR); \
	HookInitExtension(VK_KHR_surface, GetPhysicalDeviceSurfaceSupportKHR); \
	HookInitExtension(VK_KHR_surface, GetPhysicalDeviceSurfaceCapabilitiesKHR); \
	HookInitExtension(VK_KHR_surface, GetPhysicalDeviceSurfaceFormatsKHR); \
	HookInitExtension(VK_KHR_surface, GetPhysicalDeviceSurfacePresentModesKHR); \
	HookInitExtension(DEBUG_REPORT, DbgCreateMsgCallback); \
	HookInitExtension(DEBUG_REPORT, DbgDestroyMsgCallback); \
	HookInitInstance_PlatformSpecific()

#define HookInitVulkanDeviceExts() \
	HookInitExtension(VK_LUNARG_DEBUG_MARKER, CmdDbgMarkerBegin); \
	HookInitExtension(VK_LUNARG_DEBUG_MARKER, CmdDbgMarkerEnd); \
	HookInitExtension(VK_LUNARG_DEBUG_MARKER, DbgSetObjectTag); \
	HookInitExtension(VK_LUNARG_DEBUG_MARKER, DbgSetObjectName); \
	HookInitExtension(VK_KHR_swapchain, CreateSwapchainKHR); \
	HookInitExtension(VK_KHR_swapchain, DestroySwapchainKHR); \
	HookInitExtension(VK_KHR_swapchain, GetSwapchainImagesKHR); \
	HookInitExtension(VK_KHR_swapchain, AcquireNextImageKHR); \
	HookInitExtension(VK_KHR_swapchain, QueuePresentKHR);

#define DefineHooks() \
	HookDefine3(VkResult, vkEnumeratePhysicalDevices, VkInstance, instance, uint32_t*, pPhysicalDeviceCount, VkPhysicalDevice*, pPhysicalDevices); \
	HookDefine2(void, vkGetPhysicalDeviceFeatures, VkPhysicalDevice, physicalDevice, VkPhysicalDeviceFeatures*, pFeatures); \
	HookDefine3(void, vkGetPhysicalDeviceFormatProperties, VkPhysicalDevice, physicalDevice, VkFormat, format, VkFormatProperties*, pFormatProperties); \
	HookDefine7(VkResult, vkGetPhysicalDeviceImageFormatProperties, VkPhysicalDevice, physicalDevice, VkFormat, format, VkImageType, type, VkImageTiling, tiling, VkImageUsageFlags, usage, VkImageCreateFlags, flags, VkImageFormatProperties*, pImageFormatProperties); \
	HookDefine8(void, vkGetPhysicalDeviceSparseImageFormatProperties, VkPhysicalDevice, physicalDevice, VkFormat, format, VkImageType, type, VkSampleCountFlagBits, samples, VkImageUsageFlags, usage, VkImageTiling, tiling, uint32_t*, pNumProperties, VkSparseImageFormatProperties*, pProperties); \
	HookDefine2(void, vkGetPhysicalDeviceProperties, VkPhysicalDevice, physicalDevice, VkPhysicalDeviceProperties*, pProperties); \
	HookDefine3(void, vkGetPhysicalDeviceQueueFamilyProperties, VkPhysicalDevice, physicalDevice, uint32_t*, pCount, VkQueueFamilyProperties*, pQueueFamilyProperties); \
	HookDefine2(void, vkGetPhysicalDeviceMemoryProperties, VkPhysicalDevice, physicalDevice, VkPhysicalDeviceMemoryProperties*, pMemoryProperties); \
	HookDefine4(VkResult, vkCreateDevice, VkPhysicalDevice, physicalDevice, const VkDeviceCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkDevice*, pDevice); \
	HookDefine2(void, vkDestroyDevice, VkDevice, device, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(void, vkGetDeviceQueue, VkDevice, device, uint32_t, queueFamilyIndex, uint32_t, queueIndex, VkQueue*, pQueue); \
	HookDefine4(VkResult, vkQueueSubmit, VkQueue, queue, uint32_t, submitCount, const VkSubmitInfo*, pSubmits, VkFence, fence); \
	HookDefine1(VkResult, vkQueueWaitIdle, VkQueue, queue); \
	HookDefine1(VkResult, vkDeviceWaitIdle, VkDevice, device); \
	HookDefine4(VkResult, vkAllocateMemory, VkDevice, device, const VkMemoryAllocateInfo*, pAllocInfo, const VkAllocationCallbacks*, pAllocator, VkDeviceMemory*, pMemory); \
	HookDefine3(void, vkFreeMemory, VkDevice, device, VkDeviceMemory, mem, const VkAllocationCallbacks*, pAllocator); \
	HookDefine6(VkResult, vkMapMemory, VkDevice, device, VkDeviceMemory, mem, VkDeviceSize, offset, VkDeviceSize, size, VkMemoryMapFlags, flags, void**, ppData); \
	HookDefine2(void, vkUnmapMemory, VkDevice, device, VkDeviceMemory, mem); \
	HookDefine3(VkResult, vkFlushMappedMemoryRanges, VkDevice, device, uint32_t, memRangeCount, const VkMappedMemoryRange*, pMemRanges); \
	HookDefine3(VkResult, vkInvalidateMappedMemoryRanges, VkDevice, device, uint32_t, memRangeCount, const VkMappedMemoryRange*, pMemRanges); \
	HookDefine3(void, vkGetDeviceMemoryCommitment, VkDevice, device, VkDeviceMemory, memory, VkDeviceSize*, pCommittedMemoryInBytes); \
	HookDefine4(VkResult, vkBindBufferMemory, VkDevice, device, VkBuffer, buffer, VkDeviceMemory, mem, VkDeviceSize, memOffset); \
	HookDefine4(VkResult, vkBindImageMemory, VkDevice, device, VkImage, image, VkDeviceMemory, mem, VkDeviceSize, memOffset); \
	HookDefine4(VkResult, vkQueueBindSparse, VkQueue, queue, uint32_t, bindInfoCount, const VkBindSparseInfo*, pBindInfo, VkFence, fence); \
	HookDefine4(VkResult, vkCreateBuffer, VkDevice, device, const VkBufferCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkBuffer*, pBuffer); \
	HookDefine3(void, vkDestroyBuffer, VkDevice, device, VkBuffer, buffer, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateBufferView, VkDevice, device, const VkBufferViewCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkBufferView*, pView); \
	HookDefine3(void, vkDestroyBufferView, VkDevice, device, VkBufferView, bufferView, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateImage, VkDevice, device, const VkImageCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkImage*, pImage); \
	HookDefine3(void, vkDestroyImage, VkDevice, device, VkImage, image, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(void, vkGetImageSubresourceLayout, VkDevice, device, VkImage, image, const VkImageSubresource*, pSubresource, VkSubresourceLayout*, pLayout); \
	HookDefine3(void, vkGetBufferMemoryRequirements, VkDevice, device, VkBuffer, buffer, VkMemoryRequirements*, pMemoryRequirements); \
	HookDefine3(void, vkGetImageMemoryRequirements, VkDevice, device, VkImage, image, VkMemoryRequirements*, pMemoryRequirements); \
	HookDefine4(void, vkGetImageSparseMemoryRequirements, VkDevice, device, VkImage, image, uint32_t*, pNumRequirements, VkSparseImageMemoryRequirements*, pSparseMemoryRequirements); \
	HookDefine4(VkResult, vkCreateImageView, VkDevice, device, const VkImageViewCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkImageView*, pView); \
	HookDefine3(void, vkDestroyImageView, VkDevice, device, VkImageView, imageView, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateShaderModule, VkDevice, device, const VkShaderModuleCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkShaderModule*, pShaderModule); \
	HookDefine3(void, vkDestroyShaderModule, VkDevice, device, VkShaderModule, shaderModule, const VkAllocationCallbacks*, pAllocator); \
	HookDefine6(VkResult, vkCreateGraphicsPipelines, VkDevice, device, VkPipelineCache, pipelineCache, uint32_t, count, const VkGraphicsPipelineCreateInfo*, pCreateInfos, const VkAllocationCallbacks*, pAllocator, VkPipeline*, pPipelines); \
	HookDefine6(VkResult, vkCreateComputePipelines, VkDevice, device, VkPipelineCache, pipelineCache, uint32_t, count, const VkComputePipelineCreateInfo*, pCreateInfos, const VkAllocationCallbacks*, pAllocator, VkPipeline*, pPipelines); \
	HookDefine3(void, vkDestroyPipeline, VkDevice, device, VkPipeline, pipeline, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreatePipelineCache, VkDevice, device, const VkPipelineCacheCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkPipelineCache*, pPipelineCache); \
	HookDefine3(void, vkDestroyPipelineCache, VkDevice, device, VkPipelineCache, pipelineCache, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkGetPipelineCacheData, VkDevice, device, VkPipelineCache, pipelineCache, size_t*, pDataSize, void*, pData); \
	HookDefine4(VkResult, vkMergePipelineCaches, VkDevice, device, VkPipelineCache, pipelineCache, uint32_t, srcCacheCount, const VkPipelineCache*, pSrcCaches); \
	HookDefine4(VkResult, vkCreatePipelineLayout, VkDevice, device, const VkPipelineLayoutCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkPipelineLayout*, pPipelineLayout); \
	HookDefine3(void, vkDestroyPipelineLayout, VkDevice, device, VkPipelineLayout, pipelineLayout, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateSemaphore, VkDevice, device, const VkSemaphoreCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkSemaphore*, pSemaphore); \
	HookDefine3(void, vkDestroySemaphore, VkDevice, device, VkSemaphore, semaphore, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateFence, VkDevice, device, const VkFenceCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkFence*, pFence); \
	HookDefine3(void, vkDestroyFence, VkDevice, device, VkFence, fence, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateEvent, VkDevice, device, const VkEventCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkEvent*, pEvent); \
	HookDefine3(void, vkDestroyEvent, VkDevice, device, VkEvent, event, const VkAllocationCallbacks*, pAllocator); \
	HookDefine2(VkResult, vkGetEventStatus, VkDevice, device, VkEvent, event); \
	HookDefine2(VkResult, vkSetEvent, VkDevice, device, VkEvent, event); \
	HookDefine2(VkResult, vkResetEvent, VkDevice, device, VkEvent, event); \
	HookDefine4(VkResult, vkCreateQueryPool, VkDevice, device, const VkQueryPoolCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkQueryPool*, pQueryPool); \
	HookDefine3(void, vkDestroyQueryPool, VkDevice, device, VkQueryPool, queryPool, const VkAllocationCallbacks*, pAllocator); \
	HookDefine8(VkResult, vkGetQueryPoolResults, VkDevice, device, VkQueryPool, queryPool, uint32_t, startQuery, uint32_t, queryCount, size_t, dataSize, void*, pData, VkDeviceSize, stride, VkQueryResultFlags, flags); \
	HookDefine2(VkResult, vkGetFenceStatus, VkDevice, device, VkFence, fence); \
	HookDefine3(VkResult, vkResetFences, VkDevice, device, uint32_t, fenceCount, const VkFence*, pFences); \
	HookDefine5(VkResult, vkWaitForFences, VkDevice, device, uint32_t, fenceCount, const VkFence*, pFences, VkBool32, waitAll, uint64_t, timeout); \
	HookDefine4(VkResult, vkCreateSampler, VkDevice, device, const VkSamplerCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkSampler*, pSampler); \
	HookDefine3(void, vkDestroySampler, VkDevice, device, VkSampler, sampler, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateDescriptorSetLayout, VkDevice, device, const VkDescriptorSetLayoutCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkDescriptorSetLayout*, pSetLayout); \
	HookDefine3(void, vkDestroyDescriptorSetLayout, VkDevice, device, VkDescriptorSetLayout, descriptorSetLayout, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateDescriptorPool, VkDevice, device, const VkDescriptorPoolCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkDescriptorPool*, pDescriptorPool); \
	HookDefine3(void, vkDestroyDescriptorPool, VkDevice, device, VkDescriptorPool, descriptorPool, const VkAllocationCallbacks*, pAllocator); \
	HookDefine3(VkResult, vkResetDescriptorPool, VkDevice, device, VkDescriptorPool, descriptorPool, VkDescriptorPoolResetFlags, flags); \
	HookDefine3(VkResult, vkAllocateDescriptorSets, VkDevice, device, const VkDescriptorSetAllocateInfo*, pAllocateInfo, VkDescriptorSet*, pDescriptorSets); \
	HookDefine5(void, vkUpdateDescriptorSets, VkDevice, device, uint32_t, writeCount, const VkWriteDescriptorSet*, pDescriptorWrites, uint32_t, copyCount, const VkCopyDescriptorSet*, pDescriptorCopies); \
	HookDefine4(VkResult, vkFreeDescriptorSets, VkDevice, device, VkDescriptorPool, descriptorPool, uint32_t, count, const VkDescriptorSet*, pDescriptorSets); \
	HookDefine4(VkResult, vkCreateCommandPool, VkDevice, device, const VkCommandPoolCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkCommandPool*, pCommandPool); \
	HookDefine3(void, vkDestroyCommandPool, VkDevice, device, VkCommandPool, commandPool, const VkAllocationCallbacks*, pAllocator); \
	HookDefine3(VkResult, vkResetCommandPool, VkDevice, device, VkCommandPool, commandPool, VkCommandPoolResetFlags, flags); \
	HookDefine3(VkResult, vkAllocateCommandBuffers, VkDevice, device, const VkCommandBufferAllocateInfo*, pCreateInfo, VkCommandBuffer*, pCommandBuffers); \
	HookDefine4(void, vkFreeCommandBuffers, VkDevice, device, VkCommandPool, commandPool, uint32_t, commandBufferCount, const VkCommandBuffer*, pCommandBuffers); \
	HookDefine2(VkResult, vkBeginCommandBuffer, VkCommandBuffer, commandBuffer, const VkCommandBufferBeginInfo*, pBeginInfo); \
	HookDefine1(VkResult, vkEndCommandBuffer, VkCommandBuffer, commandBuffer); \
	HookDefine2(VkResult, vkResetCommandBuffer, VkCommandBuffer, commandBuffer, VkCommandBufferResetFlags, flags); \
	HookDefine3(void, vkCmdBindPipeline, VkCommandBuffer, commandBuffer, VkPipelineBindPoint, pipelineBindPoint, VkPipeline, pipeline); \
	HookDefine3(void, vkCmdSetViewport, VkCommandBuffer, commandBuffer, uint32_t, viewportCount, const VkViewport*, pViewports); \
	HookDefine3(void, vkCmdSetScissor, VkCommandBuffer, commandBuffer, uint32_t, scissorCount, const VkRect2D*, pScissors); \
	HookDefine2(void, vkCmdSetLineWidth, VkCommandBuffer, commandBuffer, float, lineWidth); \
	HookDefine4(void, vkCmdSetDepthBias, VkCommandBuffer, commandBuffer, float, depthBias, float, depthBiasClamp, float, slopeScaledDepthBias); \
	HookDefine2(void, vkCmdSetBlendConstants, VkCommandBuffer, commandBuffer, const float*, blendConst); \
	HookDefine3(void, vkCmdSetDepthBounds, VkCommandBuffer, commandBuffer, float, minDepthBounds, float, maxDepthBounds); \
	HookDefine3(void, vkCmdSetStencilCompareMask, VkCommandBuffer, commandBuffer, VkStencilFaceFlags, faceMask, uint32_t, compareMask); \
	HookDefine3(void, vkCmdSetStencilWriteMask, VkCommandBuffer, commandBuffer, VkStencilFaceFlags, faceMask, uint32_t, writeMask); \
	HookDefine3(void, vkCmdSetStencilReference, VkCommandBuffer, commandBuffer, VkStencilFaceFlags, faceMask, uint32_t, reference); \
	HookDefine8(void, vkCmdBindDescriptorSets, VkCommandBuffer, commandBuffer, VkPipelineBindPoint, pipelineBindPoint, VkPipelineLayout, layout, uint32_t, firstSet, uint32_t, setCount, const VkDescriptorSet*, pDescriptorSets, uint32_t, dynamicOffsetCount, const uint32_t*, pDynamicOffsets); \
	HookDefine4(void, vkCmdBindIndexBuffer, VkCommandBuffer, commandBuffer, VkBuffer, buffer, VkDeviceSize, offset, VkIndexType, indexType); \
	HookDefine5(void, vkCmdBindVertexBuffers, VkCommandBuffer, commandBuffer, uint32_t, startBinding, uint32_t, bindingCount, const VkBuffer*, pBuffers, const VkDeviceSize*, pOffsets); \
	HookDefine5(void, vkCmdDraw, VkCommandBuffer, commandBuffer, uint32_t, vertexCount, uint32_t, instanceCount, uint32_t, firstVertex, uint32_t, firstInstance); \
	HookDefine6(void, vkCmdDrawIndexed, VkCommandBuffer, commandBuffer, uint32_t, indexCount, uint32_t, instanceCount, uint32_t, firstIndex, int32_t, vertexOffset, uint32_t, firstInstance); \
	HookDefine5(void, vkCmdDrawIndirect, VkCommandBuffer, commandBuffer, VkBuffer, buffer, VkDeviceSize, offset, uint32_t, count, uint32_t, stride); \
	HookDefine5(void, vkCmdDrawIndexedIndirect, VkCommandBuffer, commandBuffer, VkBuffer, buffer, VkDeviceSize, offset, uint32_t, count, uint32_t, stride); \
	HookDefine4(void, vkCmdDispatch, VkCommandBuffer, commandBuffer, uint32_t, x, uint32_t, y, uint32_t, z); \
	HookDefine3(void, vkCmdDispatchIndirect, VkCommandBuffer, commandBuffer, VkBuffer, buffer, VkDeviceSize, offset); \
	HookDefine6(void, vkCmdCopyBufferToImage, VkCommandBuffer, commandBuffer, VkBuffer, srcBuffer, VkImage, destImage, VkImageLayout, destImageLayout, uint32_t, regionCount, const VkBufferImageCopy*, pRegions); \
	HookDefine6(void, vkCmdCopyImageToBuffer, VkCommandBuffer, commandBuffer, VkImage, srcImage, VkImageLayout, srcImageLayout, VkBuffer, destBuffer, uint32_t, regionCount, const VkBufferImageCopy*, pRegions); \
	HookDefine5(void, vkCmdCopyBuffer, VkCommandBuffer, commandBuffer, VkBuffer, srcBuffer, VkBuffer, destBuffer, uint32_t, regionCount, const VkBufferCopy*, pRegions); \
	HookDefine7(void, vkCmdCopyImage, VkCommandBuffer, commandBuffer, VkImage, srcImage, VkImageLayout, srcImageLayout, VkImage, destImage, VkImageLayout, destImageLayout, uint32_t, regionCount, const VkImageCopy*, pRegions); \
	HookDefine8(void, vkCmdBlitImage, VkCommandBuffer, commandBuffer, VkImage, srcImage, VkImageLayout, srcImageLayout, VkImage, destImage, VkImageLayout, destImageLayout, uint32_t, regionCount, const VkImageBlit*, pRegions, VkFilter, filter); \
	HookDefine7(void, vkCmdResolveImage, VkCommandBuffer, commandBuffer, VkImage, srcImage, VkImageLayout, srcImageLayout, VkImage, destImage, VkImageLayout, destImageLayout, uint32_t, regionCount, const VkImageResolve*, pRegions); \
	HookDefine5(void, vkCmdUpdateBuffer, VkCommandBuffer, commandBuffer, VkBuffer, destBuffer, VkDeviceSize, destOffset, VkDeviceSize, dataSize, const uint32_t*, pData); \
	HookDefine5(void, vkCmdFillBuffer, VkCommandBuffer, commandBuffer, VkBuffer, destBuffer, VkDeviceSize, destOffset, VkDeviceSize, fillSize, uint32_t, data); \
	HookDefine6(void, vkCmdPushConstants, VkCommandBuffer, commandBuffer, VkPipelineLayout, layout, VkShaderStageFlags, stageFlags, uint32_t, start, uint32_t, length, const void*, values); \
	HookDefine6(void, vkCmdClearColorImage, VkCommandBuffer, commandBuffer, VkImage, image, VkImageLayout, imageLayout, const VkClearColorValue*, pColor, uint32_t, rangeCount, const VkImageSubresourceRange*, pRanges); \
	HookDefine6(void, vkCmdClearDepthStencilImage, VkCommandBuffer, commandBuffer, VkImage, image, VkImageLayout, imageLayout, const VkClearDepthStencilValue*, pDepthStencil, uint32_t, rangeCount, const VkImageSubresourceRange*, pRanges); \
	HookDefine5(void, vkCmdClearAttachments, VkCommandBuffer, commandBuffer, uint32_t, attachmentCount, const VkClearAttachment*, pAttachments, uint32_t, rectCount, const VkClearRect*, pRects); \
	HookDefine6(void, vkCmdPipelineBarrier, VkCommandBuffer, commandBuffer, VkPipelineStageFlags, srcStageMask, VkPipelineStageFlags, destStageMask, VkBool32, byRegion, uint32_t, memBarrierCount, const void* const*, ppMemBarriers); \
	HookDefine4(void, vkCmdWriteTimestamp, VkCommandBuffer, commandBuffer, VkPipelineStageFlagBits, pipelineStage, VkQueryPool, queryPool, uint32_t, entry); \
	HookDefine8(void, vkCmdCopyQueryPoolResults, VkCommandBuffer, commandBuffer, VkQueryPool, queryPool, uint32_t, startQuery, uint32_t, queryCount, VkBuffer, dstBuffer, VkDeviceSize, dstOffset, VkDeviceSize, stride, VkQueryResultFlags, flags); \
	HookDefine4(void, vkCmdBeginQuery, VkCommandBuffer, commandBuffer, VkQueryPool, queryPool, uint32_t, slot, VkQueryControlFlags, flags); \
	HookDefine3(void, vkCmdEndQuery, VkCommandBuffer, commandBuffer, VkQueryPool, queryPool, uint32_t, slot); \
	HookDefine4(void, vkCmdResetQueryPool, VkCommandBuffer, commandBuffer, VkQueryPool, queryPool, uint32_t, startQuery, uint32_t, queryCount); \
	HookDefine3(void, vkCmdSetEvent, VkCommandBuffer, commandBuffer, VkEvent, event, VkPipelineStageFlags, stageMask); \
	HookDefine3(void, vkCmdResetEvent, VkCommandBuffer, commandBuffer, VkEvent, event, VkPipelineStageFlags, stageMask); \
	HookDefine7(void, vkCmdWaitEvents, VkCommandBuffer, commandBuffer, uint32_t, eventCount, const VkEvent*, pEvents, VkPipelineStageFlags, srcStageMask, VkPipelineStageFlags, destStageMask, uint32_t, memBarrierCount, const void* const*, ppMemBarriers); \
	HookDefine4(VkResult, vkCreateFramebuffer, VkDevice, device, const VkFramebufferCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkFramebuffer*, pFramebuffer); \
	HookDefine3(void, vkDestroyFramebuffer, VkDevice, device, VkFramebuffer, framebuffer, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkCreateRenderPass, VkDevice, device, const VkRenderPassCreateInfo*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkRenderPass*, pRenderPass); \
	HookDefine3(void, vkDestroyRenderPass, VkDevice, device, VkRenderPass, renderPass, const VkAllocationCallbacks*, pAllocator); \
	HookDefine3(void, vkGetRenderAreaGranularity, VkDevice, device, VkRenderPass, renderPass, VkExtent2D*, pGranularity); \
	HookDefine3(void, vkCmdBeginRenderPass, VkCommandBuffer, commandBuffer, const VkRenderPassBeginInfo*, pRenderPassBegin, VkSubpassContents, contents); \
	HookDefine2(void, vkCmdNextSubpass, VkCommandBuffer, commandBuffer, VkSubpassContents, contents); \
	HookDefine3(void, vkCmdExecuteCommands, VkCommandBuffer, commandBuffer, uint32_t, commandBuffersCount, const VkCommandBuffer*, pCommandBuffers); \
	HookDefine1(void, vkCmdEndRenderPass, VkCommandBuffer, commandBuffer); \
	HookDefine5(VkResult, vkDbgCreateMsgCallback, VkInstance, instance, VkFlags, msgFlags, const PFN_vkDbgMsgCallback, pfnMsgCallback, void*, pUserData, VkDbgMsgCallback*, pMsgCallback); \
	HookDefine2(VkResult, vkDbgDestroyMsgCallback, VkInstance, instance, VkDbgMsgCallback, msgCallback); \
	HookDefine2(void, vkCmdDbgMarkerBegin, VkCommandBuffer, commandBuffer, const char*, pMarker); \
	HookDefine1(void, vkCmdDbgMarkerEnd, VkCommandBuffer, commandBuffer); \
	HookDefine5(VkResult, vkDbgSetObjectTag, VkDevice, device, VkDbgObjectType, objType, uint64_t, object, size_t, tagSize, const void*, pTag); \
	HookDefine5(VkResult, vkDbgSetObjectName, VkDevice, device, VkDbgObjectType, objType, uint64_t, object, size_t, nameSize, const char*, pName); \
	HookDefine4(VkResult, vkGetPhysicalDeviceSurfaceSupportKHR, VkPhysicalDevice, physicalDevice, uint32_t, queueFamilyIndex, VkSurfaceKHR, surface, VkBool32*, pSupported); \
	HookDefine3(VkResult, vkGetPhysicalDeviceSurfaceCapabilitiesKHR, VkPhysicalDevice, physicalDevice, VkSurfaceKHR, surface, VkSurfaceCapabilitiesKHR*, pSurfaceProperties); \
	HookDefine4(VkResult, vkGetPhysicalDeviceSurfaceFormatsKHR, VkPhysicalDevice, physicalDevice, VkSurfaceKHR, surface, uint32_t*, pSurfaceFormatCount, VkSurfaceFormatKHR*, pSurfaceFormats); \
	HookDefine4(VkResult, vkGetPhysicalDeviceSurfacePresentModesKHR, VkPhysicalDevice, physicalDevice, VkSurfaceKHR, surface, uint32_t*, pPresentModeCount, VkPresentModeKHR*, pPresentModes); \
	HookDefine4(VkResult, vkCreateSwapchainKHR, VkDevice, device, const VkSwapchainCreateInfoKHR*, pCreateInfo, const VkAllocationCallbacks*, pAllocator, VkSwapchainKHR*, pSwapchain); \
	HookDefine3(void, vkDestroySwapchainKHR, VkDevice, device, VkSwapchainKHR, swapchain, const VkAllocationCallbacks*, pAllocator); \
	HookDefine4(VkResult, vkGetSwapchainImagesKHR, VkDevice, device, VkSwapchainKHR, swapchain, uint32_t*, pCount, VkImage*, pSwapchainImages); \
	HookDefine6(VkResult, vkAcquireNextImageKHR, VkDevice, device, VkSwapchainKHR, swapchain, uint64_t, timeout, VkSemaphore, semaphore, VkFence, fence, uint32_t*, pImageIndex); \
	HookDefine2(VkResult, vkQueuePresentKHR, VkQueue, queue, VkPresentInfoKHR*, pPresentInfo); \
	HookDefine3(void, vkDestroySurfaceKHR, VkInstance, instance, VkSurfaceKHR, surface, const VkAllocationCallbacks*, pAllocator); \
	HookDefine_PlatformSpecific()

struct VkLayerInstanceDispatchTableExtended : VkLayerInstanceDispatchTable
{
	// extensions here
};

struct VkLayerDispatchTableExtended : VkLayerDispatchTable
{
	// VK_LUNARG_DEBUG_MARKER
	PFN_vkCmdDbgMarkerBegin CmdDbgMarkerBegin;
	PFN_vkCmdDbgMarkerEnd CmdDbgMarkerEnd;
	PFN_vkDbgSetObjectTag DbgSetObjectTag;
	PFN_vkDbgSetObjectName DbgSetObjectName;
};
