
/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2015-2026 Baldur Karlsson
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

#include <QMap>
#include <QString>
#include "Code/Interface/QRDInterface.h"

// Built-in test texture types
enum class BuiltinTexture
{
  White,
  Black,
  Gray,
  Checkerboard,
  UVGradient,
  NormalUp,
  Count
};

// Stores loaded image data in RGBA8 or RGBA32F format
struct LoadedImageData
{
  int width = 0;
  int height = 0;
  int channels = 0;
  bool isHDR = false;
  bytebuf data;    // raw pixel bytes (RGBA8 or RGBA32F)
};

// Tracks a single texture replacement
struct TextureReplacement
{
  ResourceId originalId;
  ResourceId proxyId;
  QString sourcePath;    // empty for built-in textures
  BuiltinTexture builtinType = BuiltinTexture::Count;    // Count = not a builtin
};

class TextureReplacer
{
public:
  TextureReplacer(ICaptureContext &ctx);
  ~TextureReplacer();

  // Load an image from disk (PNG/JPG/BMP/TGA/HDR/DDS/EXR)
  // Returns true on success, fills out imageData
  bool LoadImageFile(const QString &path, LoadedImageData &imageData);

  // Generate a built-in test texture at the given dimensions
  bool GenerateBuiltinTexture(BuiltinTexture type, int width, int height, LoadedImageData &imageData);

  // Resize image data to match target dimensions (if needed)
  // Modifies imageData in-place
  bool ResizeIfNeeded(LoadedImageData &imageData, int targetWidth, int targetHeight);

  // Replace a captured texture with loaded image data
  // This runs on the replay thread via AsyncInvoke
  void ReplaceTexture(ResourceId originalTexId, const LoadedImageData &imageData);

  // Replace a captured texture with a built-in test texture
  void ReplaceWithBuiltin(ResourceId originalTexId, BuiltinTexture type);

  // Replace a captured texture with a file from disk
  void ReplaceFromFile(ResourceId originalTexId, const QString &filePath);

  // Restore the original texture (remove replacement)
  void RestoreTexture(ResourceId originalTexId);

  // Restore all replaced textures
  void RestoreAll();

  // Check if a texture has been replaced
  bool IsReplaced(ResourceId texId) const;

  // Get the replacement info for a texture
  const TextureReplacement *GetReplacement(ResourceId texId) const;

  // Get all active replacements
  const QMap<ResourceId, TextureReplacement> &GetAllReplacements() const { return m_Replacements; }

  // Called when capture is closed to clean up
  void OnCaptureClosed();

private:
  ICaptureContext &m_Ctx;
  QMap<ResourceId, TextureReplacement> m_Replacements;
};
