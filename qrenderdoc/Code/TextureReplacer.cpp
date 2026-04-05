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

#include "TextureReplacer.h"

#include <QFileInfo>
#include <QImage>
#include <cmath>
#include <cstring>

TextureReplacer::TextureReplacer(ICaptureContext &ctx) : m_Ctx(ctx)
{
}

TextureReplacer::~TextureReplacer()
{
  // Don't call RestoreAll in destructor - capture may already be closed
}

bool TextureReplacer::LoadImageFile(const QString &path, LoadedImageData &imageData)
{
  QFileInfo fi(path);
  if(!fi.exists())
  {
    qWarning() << "TextureReplacer: File does not exist:" << path;
    return false;
  }

  // Use QImage to load standard image formats (PNG, JPG, BMP, TGA, etc.)
  QImage img(path);
  if(img.isNull())
  {
    qWarning() << "TextureReplacer: Failed to load image:" << path;
    return false;
  }

  // Convert to RGBA8 format
  QImage rgba = img.convertToFormat(QImage::Format_RGBA8888);

  imageData.width = rgba.width();
  imageData.height = rgba.height();
  imageData.channels = 4;
  imageData.isHDR = false;

  size_t dataSize = (size_t)rgba.width() * rgba.height() * 4;
  imageData.data.resize(dataSize);

  // Copy scanlines (QImage may have padding per row)
  for(int y = 0; y < rgba.height(); y++)
  {
    const uchar *srcLine = rgba.constScanLine(y);
    memcpy(imageData.data.data() + (size_t)y * rgba.width() * 4, srcLine, (size_t)rgba.width() * 4);
  }

  qWarning() << "TextureReplacer: Loaded image" << path << rgba.width() << "x" << rgba.height();
  return true;
}

bool TextureReplacer::GenerateBuiltinTexture(BuiltinTexture type, int width, int height,
                                              LoadedImageData &imageData)
{
  imageData.width = width;
  imageData.height = height;
  imageData.channels = 4;
  imageData.isHDR = false;
  size_t dataSize = (size_t)width * height * 4;
  imageData.data.resize(dataSize);
  byte *pixels = imageData.data.data();

  for(int y = 0; y < height; y++)
  {
    for(int x = 0; x < width; x++)
    {
      size_t idx = ((size_t)y * width + x) * 4;
      switch(type)
      {
        case BuiltinTexture::White:
          pixels[idx + 0] = 255;
          pixels[idx + 1] = 255;
          pixels[idx + 2] = 255;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::Black:
          pixels[idx + 0] = 0;
          pixels[idx + 1] = 0;
          pixels[idx + 2] = 0;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::Gray:
          pixels[idx + 0] = 128;
          pixels[idx + 1] = 128;
          pixels[idx + 2] = 128;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::Checkerboard:
        {
          int cellSize = qMax(1, qMin(width, height) / 16);
          bool isWhite = ((x / cellSize) + (y / cellSize)) % 2 == 0;
          byte v = isWhite ? 255 : 0;
          pixels[idx + 0] = v;
          pixels[idx + 1] = v;
          pixels[idx + 2] = v;
          pixels[idx + 3] = 255;
          break;
        }

        case BuiltinTexture::UVGradient:
          pixels[idx + 0] = (byte)(255.0f * x / qMax(1, width - 1));
          pixels[idx + 1] = (byte)(255.0f * y / qMax(1, height - 1));
          pixels[idx + 2] = 0;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::NormalUp:
          pixels[idx + 0] = 128;
          pixels[idx + 1] = 128;
          pixels[idx + 2] = 255;
          pixels[idx + 3] = 255;
          break;

        default: break;
      }
    }
  }

  qWarning() << "TextureReplacer: Generated builtin texture type" << (int)type << width << "x"
             << height;
  return true;
}

bool TextureReplacer::ResizeIfNeeded(LoadedImageData &imageData, int targetWidth, int targetHeight)
{
  if(imageData.width == targetWidth && imageData.height == targetHeight)
    return true;

  qWarning() << "TextureReplacer: Resizing from" << imageData.width << "x" << imageData.height
             << "to" << targetWidth << "x" << targetHeight;

  // Use QImage for high-quality resizing
  QImage src((const uchar *)imageData.data.data(), imageData.width, imageData.height,
             imageData.width * 4, QImage::Format_RGBA8888);
  QImage dst = src.scaled(targetWidth, targetHeight, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
  dst = dst.convertToFormat(QImage::Format_RGBA8888);

  size_t dataSize = (size_t)targetWidth * targetHeight * 4;
  imageData.data.resize(dataSize);
  for(int y = 0; y < targetHeight; y++)
  {
    const uchar *srcLine = dst.constScanLine(y);
    memcpy(imageData.data.data() + (size_t)y * targetWidth * 4, srcLine, (size_t)targetWidth * 4);
  }

  imageData.width = targetWidth;
  imageData.height = targetHeight;
  return true;
}

void TextureReplacer::ReplaceTexture(ResourceId originalTexId, const LoadedImageData &imageData)
{
  // Build replacement data (copy so we can capture in lambda)
  LoadedImageData img = imageData;

  qWarning() << "TextureReplacer: Starting replacement for texture"
             << m_Ctx.GetResourceName(originalTexId) << "size" << img.width << "x" << img.height
             << "dataSize" << img.data.size();

  m_Ctx.Replay().AsyncInvoke([this, originalTexId, img](IReplayController *r) {
    // Find the original texture description
    const rdcarray<TextureDescription> &textures = r->GetTextures();
    const TextureDescription *origTex = nullptr;
    for(const TextureDescription &t : textures)
    {
      if(t.resourceId == originalTexId)
      {
        origTex = &t;
        break;
      }
    }

    if(!origTex)
    {
      qCritical() << "TextureReplacer: Could not find original texture description for"
                   << ToQStr(originalTexId);
      return;
    }

    qWarning() << "TextureReplacer: Original texture format:"
               << ToQStr(origTex->format.Name()) << "dim:" << origTex->width << "x"
               << origTex->height << "mips:" << origTex->mips
               << "arraysize:" << origTex->arraysize;

    // Create proxy with RGBA8 UNORM format since we're uploading raw RGBA8 byte data.
    // Using the original format (e.g. BC1 compressed) would cause a data size mismatch
    // because SetProxyTextureData expects data in the proxy's native format.
    TextureDescription proxyDesc = *origTex;
    proxyDesc.mips = 1;
    proxyDesc.arraysize = 1;
    proxyDesc.msSamp = 1;
    proxyDesc.msQual = 0;
    proxyDesc.cubemap = false;

    // Override to RGBA8 UNORM - matches the byte data we upload
    proxyDesc.format.type = ResourceFormatType::Regular;
    proxyDesc.format.compCount = 4;
    proxyDesc.format.compByteWidth = 1;
    proxyDesc.format.compType = CompType::UNorm;
    proxyDesc.format.SetBGRAOrder(false);

    ResourceId proxyId = r->CreateProxyTexture(proxyDesc);
    if(proxyId == ResourceId())
    {
      qCritical() << "TextureReplacer: CreateProxyTexture failed!";
      return;
    }

    qWarning() << "TextureReplacer: Created proxy texture" << ToQStr(proxyId);

    // Upload the data
    Subresource sub;
    sub.mip = 0;
    sub.slice = 0;
    sub.sample = 0;

    bytebuf dataCopy = img.data;
    r->SetProxyTextureData(proxyId, sub, dataCopy.data(), dataCopy.size());

    qWarning() << "TextureReplacer: Uploaded" << dataCopy.size() << "bytes of texture data";

    // Replace the original with the proxy
    r->ReplaceResource(originalTexId, proxyId);

    qWarning() << "TextureReplacer: ReplaceResource called successfully";

    // Record the replacement on UI thread
    GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this, originalTexId, proxyId]() {
      TextureReplacement rep;
      rep.originalId = originalTexId;
      rep.proxyId = proxyId;
      m_Replacements[originalTexId] = rep;
      m_Ctx.RegisterReplacement(originalTexId, proxyId);
      qWarning() << "TextureReplacer: Replacement registered on UI thread";
    });

    // NOTE: ReplaceResource() already calls SetFrameEvent + Display() internally,
    // so no need to call SetFrameEvent again here.
    qWarning() << "TextureReplacer: Replacement complete, replay should auto-refresh";
  });
}

void TextureReplacer::ReplaceWithBuiltin(ResourceId originalTexId, BuiltinTexture type)
{
  // We need the original texture dimensions - get them from context
  const rdcarray<TextureDescription> &textures = m_Ctx.GetTextures();
  int width = 256, height = 256;
  for(const TextureDescription &t : textures)
  {
    if(t.resourceId == originalTexId)
    {
      width = (int)t.width;
      height = (int)t.height;
      break;
    }
  }

  qWarning() << "TextureReplacer: ReplaceWithBuiltin type" << (int)type << "for texture"
             << m_Ctx.GetResourceName(originalTexId) << "at" << width << "x" << height;

  LoadedImageData imageData;
  if(!GenerateBuiltinTexture(type, width, height, imageData))
    return;

  ReplaceTexture(originalTexId, imageData);
}

void TextureReplacer::ReplaceFromFile(ResourceId originalTexId, const QString &filePath)
{
  qWarning() << "TextureReplacer: ReplaceFromFile" << filePath << "for texture"
             << m_Ctx.GetResourceName(originalTexId);

  LoadedImageData imageData;
  if(!LoadImageFile(filePath, imageData))
    return;

  // Get original texture dimensions for resize
  const rdcarray<TextureDescription> &textures = m_Ctx.GetTextures();
  for(const TextureDescription &t : textures)
  {
    if(t.resourceId == originalTexId)
    {
      ResizeIfNeeded(imageData, (int)t.width, (int)t.height);
      break;
    }
  }

  ReplaceTexture(originalTexId, imageData);
}

void TextureReplacer::RestoreTexture(ResourceId originalTexId)
{
  if(!m_Replacements.contains(originalTexId))
    return;

  qWarning() << "TextureReplacer: Restoring original texture"
             << m_Ctx.GetResourceName(originalTexId);

  m_Ctx.Replay().AsyncInvoke([this, originalTexId](IReplayController *r) {
    r->RemoveReplacement(originalTexId);

    GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this, originalTexId]() {
      m_Replacements.remove(originalTexId);
      m_Ctx.UnregisterReplacement(originalTexId);
    });

    r->SetFrameEvent(m_Ctx.CurEvent(), true);
  });
}

void TextureReplacer::RestoreAll()
{
  QList<ResourceId> ids = m_Replacements.keys();
  for(const ResourceId &id : ids)
  {
    RestoreTexture(id);
  }
}

bool TextureReplacer::IsReplaced(ResourceId texId) const
{
  return m_Replacements.contains(texId);
}

const TextureReplacement *TextureReplacer::GetReplacement(ResourceId texId) const
{
  auto it = m_Replacements.find(texId);
  if(it != m_Replacements.end())
    return &it.value();
  return nullptr;
}

void TextureReplacer::OnCaptureClosed()
{
  m_Replacements.clear();
}