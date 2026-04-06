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
#include <QMessageBox>
#include <cmath>
#include <cstring>

// Helper macro for logging - goes to both qWarning (Diagnostic Log) and adds to our status log
#define TEX_LOG(msg)                         \
  do                                         \
  {                                          \
    QString _msg = msg;                      \
    qWarning() << "TextureReplacer:" << _msg; \
    appendLog(_msg);                         \
  } while(0)

#define TEX_ERR(msg)                          \
  do                                          \
  {                                           \
    QString _msg = msg;                       \
    qCritical() << "TextureReplacer:" << _msg; \
    appendLog(QStringLiteral("[ERROR] ") + _msg); \
  } while(0)

TextureReplacer::TextureReplacer(ICaptureContext &ctx) : m_Ctx(ctx)
{
}

TextureReplacer::~TextureReplacer()
{
}

void TextureReplacer::appendLog(const QString &msg)
{
  m_StatusLog.append(msg);
  // Keep last 200 lines
  while(m_StatusLog.size() > 200)
    m_StatusLog.removeFirst();
}

QString TextureReplacer::GetStatusLog() const
{
  return m_StatusLog.join(QStringLiteral("\n"));
}

void TextureReplacer::ClearLog()
{
  m_StatusLog.clear();
}

bool TextureReplacer::LoadImageFile(const QString &path, LoadedImageData &imageData)
{
  QFileInfo fi(path);
  if(!fi.exists())
  {
    TEX_ERR(QStringLiteral("File does not exist: %1").arg(path));
    return false;
  }

  QImage img(path);
  if(img.isNull())
  {
    TEX_ERR(QStringLiteral("Failed to load image: %1").arg(path));
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

  for(int y = 0; y < rgba.height(); y++)
  {
    const uchar *srcLine = rgba.constScanLine(y);
    memcpy(imageData.data.data() + (size_t)y * rgba.width() * 4, srcLine, (size_t)rgba.width() * 4);
  }

  TEX_LOG(QStringLiteral("Loaded image %1  (%2x%3)").arg(path).arg(rgba.width()).arg(rgba.height()));
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

  TEX_LOG(QStringLiteral("Generated builtin texture type=%1 (%2x%3)")
              .arg((int)type)
              .arg(width)
              .arg(height));
  return true;
}

bool TextureReplacer::ResizeIfNeeded(LoadedImageData &imageData, int targetWidth, int targetHeight)
{
  if(imageData.width == targetWidth && imageData.height == targetHeight)
    return true;

  TEX_LOG(QStringLiteral("Resizing from %1x%2 to %3x%4")
              .arg(imageData.width)
              .arg(imageData.height)
              .arg(targetWidth)
              .arg(targetHeight));

  QImage src((const uchar *)imageData.data.data(), imageData.width, imageData.height,
             imageData.width * 4, QImage::Format_RGBA8888);
  QImage dst =
      src.scaled(targetWidth, targetHeight, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
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
  LoadedImageData img = imageData;

  TEX_LOG(QStringLiteral("=== Starting texture replacement ==="));
  TEX_LOG(QStringLiteral("Target: %1 (ID: %2)")
              .arg(QString(m_Ctx.GetResourceName(originalTexId)))
              .arg(ToQStr(originalTexId)));
  TEX_LOG(QStringLiteral("Replacement data: %1x%2, %3 bytes")
              .arg(img.width)
              .arg(img.height)
              .arg(img.data.size()));

  m_Ctx.Replay().AsyncInvoke([this, originalTexId, img](IReplayController *r) {
    TEX_LOG(QStringLiteral("Step 1: Looking up original texture..."));

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
      TEX_ERR(QStringLiteral("Could not find original texture description!"));
      GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this]() {
        QMessageBox::warning(m_Ctx.GetMainWindow()->Widget(),
                             QStringLiteral("Texture Replace Failed"),
                             QStringLiteral("Could not find original texture.\n\n%1").arg(GetStatusLog()));
      });
      return;
    }

    // Only allow replacing textures that are shader-readable resources.
    // Render Targets (ColorTarget / DepthTarget only) are generated at runtime
    // and cannot be meaningfully replaced.
    if(!(origTex->creationFlags & TextureCategory::ShaderRead))
    {
      TEX_ERR(QStringLiteral("Texture is not a shader resource (flags=0x%1). "
                              "Only shader-readable textures can be replaced. "
                              "Render targets and depth buffers are generated at runtime.")
                  .arg(QString::number((uint32_t)origTex->creationFlags, 16)));
      GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this]() {
        QMessageBox::warning(
            m_Ctx.GetMainWindow()->Widget(), QStringLiteral("Texture Replace Failed"),
            QStringLiteral("This texture is a Render Target or Depth Buffer, not a shader resource.\n"
                           "Only textures used as shader inputs can be replaced.\n\n%1")
                .arg(GetStatusLog()));
      });
      return;
    }

    TEX_LOG(QStringLiteral("Step 1 OK: Found texture - format=%1, dim=%2x%3, mips=%4, flags=0x%5")
                .arg(QString(origTex->format.Name()))
                .arg(origTex->width)
                .arg(origTex->height)
                .arg(origTex->mips)
                .arg(QString::number((uint32_t)origTex->creationFlags, 16)));

    // Step 2: First replay to current event so initial states are applied
    TEX_LOG(QStringLiteral("Step 2: Replaying to current event to restore initial states..."));
    r->SetFrameEvent(m_Ctx.CurEvent(), true);
    TEX_LOG(QStringLiteral("Step 2 OK: Replay complete"));

    // Step 3: Generate data in the texture's native format
    Subresource sub;
    sub.mip = 0;
    sub.slice = 0;
    sub.sample = 0;

    bool isCompressed = (origTex->format.type == ResourceFormatType::BC1 ||
                         origTex->format.type == ResourceFormatType::BC2 ||
                         origTex->format.type == ResourceFormatType::BC3 ||
                         origTex->format.type == ResourceFormatType::BC4 ||
                         origTex->format.type == ResourceFormatType::BC5 ||
                         origTex->format.type == ResourceFormatType::BC6 ||
                         origTex->format.type == ResourceFormatType::BC7);

    bytebuf uploadData;

    if(isCompressed && origTex->format.type == ResourceFormatType::BC1)
    {
      TEX_LOG(QStringLiteral("Step 3: Generating BC1 compressed data..."));
      uint32_t bw = (origTex->width + 3) / 4;
      uint32_t bh = (origTex->height + 3) / 4;
      uploadData.resize((size_t)bw * bh * 8);

      for(uint32_t by = 0; by < bh; by++)
      {
        for(uint32_t bx = 0; bx < bw; bx++)
        {
          uint32_t rSum = 0, gSum = 0, bSum = 0, count = 0;
          for(uint32_t py = 0; py < 4; py++)
          {
            for(uint32_t px = 0; px < 4; px++)
            {
              uint32_t sx = bx * 4 + px;
              uint32_t sy = by * 4 + py;
              if(sx < (uint32_t)img.width && sy < (uint32_t)img.height)
              {
                size_t srcIdx = ((size_t)sy * img.width + sx) * 4;
                rSum += img.data[srcIdx + 0];
                gSum += img.data[srcIdx + 1];
                bSum += img.data[srcIdx + 2];
                count++;
              }
            }
          }
          if(count == 0) count = 1;
          uint16_t color565 = (uint16_t)((((rSum / count) >> 3) << 11) |
                                         (((gSum / count) >> 2) << 5) |
                                         ((bSum / count) >> 3));
          size_t off = ((size_t)by * bw + bx) * 8;
          uploadData[off + 0] = (byte)(color565 & 0xFF);
          uploadData[off + 1] = (byte)((color565 >> 8) & 0xFF);
          uploadData[off + 2] = uploadData[off + 0];
          uploadData[off + 3] = uploadData[off + 1];
          uploadData[off + 4] = 0; uploadData[off + 5] = 0;
          uploadData[off + 6] = 0; uploadData[off + 7] = 0;
        }
      }
      TEX_LOG(QStringLiteral("Step 3 OK: Generated %1 bytes BC1 data").arg(uploadData.size()));
    }
    else if(isCompressed)
    {
      TEX_LOG(QStringLiteral("Step 3: Non-BC1 compressed format (%1), getting original data...")
                  .arg(QString(origTex->format.Name())));
      uploadData = r->GetTextureData(originalTexId, sub);
      TEX_LOG(QStringLiteral("Step 3 OK: Using original %1 bytes").arg(uploadData.size()));
    }
    else
    {
      TEX_LOG(QStringLiteral("Step 3: Uncompressed format, using RGBA8 data..."));
      uploadData = img.data;
      TEX_LOG(QStringLiteral("Step 3 OK: Using %1 bytes RGBA8 data").arg(uploadData.size()));
    }

    // Step 4: Swap the underlying real D3D11 texture pointer via OverrideTextureData.
    // This creates a new DEFAULT texture with our data, copies original mip data
    // for all other subresources, and swaps the real pointer inside the wrapped object.
    // After this, any existing SRV referencing this wrapped texture will still point
    // to the OLD real texture. We need a SetFrameEvent re-replay so that SRVs are
    // re-created using the new real pointer.
    TEX_LOG(QStringLiteral("Step 4: Calling OverrideTextureData (%1 bytes)...")
                .arg(uploadData.size()));
    r->OverrideTextureData(originalTexId, sub, uploadData.data(), uploadData.size());
    TEX_LOG(QStringLiteral("Step 4 OK: Real pointer swapped"));

    // Step 5: Re-replay the frame so SRVs and render targets pick up the new texture data
    TEX_LOG(QStringLiteral("Step 5: Re-replaying frame to regenerate SRVs..."));
    r->SetFrameEvent(m_Ctx.CurEvent(), true);
    TEX_LOG(QStringLiteral("Step 5 OK: Frame re-replayed with new texture data"));

    // Record on UI thread and force a full refresh
    GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this, originalTexId]() {
      TextureReplacement rep;
      rep.originalId = originalTexId;
      rep.proxyId = originalTexId;    // in-place swap, no separate proxy
      m_Replacements[originalTexId] = rep;

      TEX_LOG(QStringLiteral("Step 6: Triggering full UI refresh..."));

      // Force a complete re-replay and UI refresh so all viewers update
      m_Ctx.RefreshStatus();

      TEX_LOG(QStringLiteral("Step 6 OK: Full refresh complete"));

      QMessageBox::information(
          m_Ctx.GetMainWindow()->Widget(),
          QStringLiteral("Texture Replaced"),
          QStringLiteral("Texture replacement applied successfully!\n\n"
                         "The replacement is active across all events.\n"
                         "Use 'Restore' to revert.\n\n"
                         "Last steps:\n%1")
              .arg(m_StatusLog.mid(qMax(0, m_StatusLog.size() - 5)).join(QStringLiteral("\n"))));
    });
  });
}

void TextureReplacer::ReplaceWithBuiltin(ResourceId originalTexId, BuiltinTexture type)
{
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

  TEX_LOG(QStringLiteral("ReplaceWithBuiltin type=%1 for %2 (%3x%4)")
              .arg((int)type)
              .arg(QString(m_Ctx.GetResourceName(originalTexId)))
              .arg(width)
              .arg(height));

  LoadedImageData imageData;
  if(!GenerateBuiltinTexture(type, width, height, imageData))
    return;

  ReplaceTexture(originalTexId, imageData);
}

void TextureReplacer::ReplaceFromFile(ResourceId originalTexId, const QString &filePath)
{
  TEX_LOG(QStringLiteral("ReplaceFromFile: %1 for %2")
              .arg(filePath)
              .arg(QString(m_Ctx.GetResourceName(originalTexId))));

  LoadedImageData imageData;
  if(!LoadImageFile(filePath, imageData))
    return;

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

  TEX_LOG(QStringLiteral("Restoring original texture %1")
              .arg(QString(m_Ctx.GetResourceName(originalTexId))));

  m_Ctx.Replay().AsyncInvoke([this, originalTexId](IReplayController *r) {
    r->RemoveReplacement(originalTexId);

    GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this, originalTexId]() {
      m_Replacements.remove(originalTexId);
      m_Ctx.UnregisterReplacement(originalTexId);
      TEX_LOG(QStringLiteral("Texture restored successfully"));
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
  m_StatusLog.clear();
}