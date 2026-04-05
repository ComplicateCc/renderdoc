/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2024-2026 Baldur Karlsson
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

#include "CBufferEditor.h"
#include <QHeaderView>
#include <QMenu>
#include <QStandardItemModel>
#include "Code/QRDUtils.h"
#include "ui_CBufferEditor.h"

CBufferEditor::CBufferEditor(ICaptureContext &ctx, QWidget *parent)
    : QFrame(parent), ui(new Ui::CBufferEditor), m_Ctx(ctx)
{
  ui->setupUi(this);

  m_Model = new QStandardItemModel(0, 3, this);
  m_Model->setHorizontalHeaderLabels({tr("Name"), tr("Type"), tr("Value")});

  ui->cbufferTree->setModel(m_Model);
  ui->cbufferTree->setContextMenuPolicy(Qt::CustomContextMenu);
  ui->cbufferTree->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
  ui->cbufferTree->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
  ui->cbufferTree->header()->setSectionResizeMode(2, QHeaderView::Stretch);

  m_Ctx.AddCaptureViewer(this);
}

CBufferEditor::~CBufferEditor()
{
  m_Ctx.RemoveCaptureViewer(this);
  delete ui;
}

void CBufferEditor::OnCaptureLoaded()
{
}

void CBufferEditor::OnCaptureClosed()
{
  ClearAll();
}

void CBufferEditor::OnEventChanged(uint32_t eventId)
{
  m_CurrentEventId = eventId;
  RefreshCBuffers();
}

void CBufferEditor::on_applyButton_clicked()
{
  ApplyEdits();
}

void CBufferEditor::on_resetButton_clicked()
{
  ResetAll();
}

void CBufferEditor::on_cbufferTree_doubleClicked(const QModelIndex &index)
{
  // Only allow editing the Value column (column 2)
  if(index.column() != 2)
    return;

  // The tree view's edit triggers handle inline editing
  ui->cbufferTree->edit(index);
}

void CBufferEditor::on_cbufferTree_customContextMenuRequested(const QPoint &pos)
{
  QModelIndex index = ui->cbufferTree->indexAt(pos);
  if(!index.isValid())
    return;

  QMenu menu;
  QAction *resetAction = menu.addAction(tr("Reset to Original"));

  QAction *chosen = menu.exec(ui->cbufferTree->viewport()->mapToGlobal(pos));
  if(chosen == resetAction)
  {
    ResetVariable(index);
  }
}

void CBufferEditor::RefreshCBuffers()
{
  ClearAll();

  if(!m_Ctx.IsCaptureLoaded())
    return;

  // Populate for each active shader stage
  const PipeState &pipe = m_Ctx.CurPipelineState();

  ShaderStage stages[] = {ShaderStage::Vertex,  ShaderStage::Hull,    ShaderStage::Domain,
                          ShaderStage::Geometry, ShaderStage::Pixel,   ShaderStage::Compute,
                          ShaderStage::Task,     ShaderStage::Mesh};

  for(ShaderStage stage : stages)
  {
    ResourceId shaderId = pipe.GetShader(stage);
    if(shaderId == ResourceId())
      continue;

    const ShaderReflection *refl = pipe.GetShaderReflection(stage);
    if(!refl)
      continue;

    PopulateStage(stage, refl);
  }

  ui->cbufferTree->expandAll();
}

void CBufferEditor::PopulateStage(ShaderStage stage, const ShaderReflection *refl)
{
  if(!refl || refl->constantBlocks.isEmpty())
    return;

  QString stageName = QString::fromUtf8(ToStr(stage).c_str());
  QStandardItem *stageItem = new QStandardItem(stageName);
  stageItem->setEditable(false);
  m_Model->appendRow(stageItem);

  for(int i = 0; i < refl->constantBlocks.count(); i++)
  {
    const ConstantBlock &cb = refl->constantBlocks[i];

    QString cbName = QString::fromUtf8(cb.name.c_str());
    if(cbName.isEmpty())
      cbName = QString(lit("CBuffer %1")).arg(i);

    QStandardItem *cbItem = new QStandardItem(cbName);
    cbItem->setEditable(false);
    stageItem->appendRow(cbItem);

    // Fetch variables for this CBuffer
    m_Ctx.Replay().AsyncInvoke([this, stage, i, cbItem](IReplayController *r) {
      rdcarray<ShaderVariable> vars = r->GetCBufferVariableContents(
          m_Ctx.CurPipelineState().GetGraphicsPipelineObject(),
          m_Ctx.CurPipelineState().GetShader(stage),
          stage, rdcstr(), i, ResourceId(), 0, 0);

      GUIInvoke::call(this, [this, cbItem, vars]() {
        for(const ShaderVariable &v : vars)
        {
          QList<QStandardItem *> row;
          QStandardItem *nameItem = new QStandardItem(QString::fromUtf8(v.name.c_str()));
          nameItem->setEditable(false);

          QString typeName = QString::fromUtf8(ToStr(v.type).c_str());
          QStandardItem *typeItem = new QStandardItem(typeName);
          typeItem->setEditable(false);

          // Format value as string
          QString valueStr;
          if(v.rows == 1 && v.columns == 1)
          {
            // Scalar
            if(v.type == VarType::Float || v.type == VarType::Half)
              valueStr = QString::number(v.value.f32v[0], 'g', 6);
            else if(v.type == VarType::SInt || v.type == VarType::SShort ||
                    v.type == VarType::SByte || v.type == VarType::SLong)
              valueStr = QString::number(v.value.s32v[0]);
            else
              valueStr = QString::number(v.value.u32v[0]);
          }
          else if(v.rows == 1)
          {
            // Vector
            QStringList components;
            for(uint32_t c = 0; c < v.columns; c++)
            {
              if(v.type == VarType::Float || v.type == VarType::Half)
                components.append(QString::number(v.value.f32v[c], 'g', 6));
              else if(v.type == VarType::SInt || v.type == VarType::SShort ||
                      v.type == VarType::SByte || v.type == VarType::SLong)
                components.append(QString::number(v.value.s32v[c]));
              else
                components.append(QString::number(v.value.u32v[c]));
            }
            valueStr = components.join(lit(", "));
          }
          else
          {
            // Matrix - show dimensions
            valueStr = QString(lit("[%1x%2 matrix]")).arg(v.rows).arg(v.columns);
          }

          QStandardItem *valueItem = new QStandardItem(valueStr);
          valueItem->setEditable(true);    // Allow editing

          row.append(nameItem);
          row.append(typeItem);
          row.append(valueItem);
          cbItem->appendRow(row);

          // Recurse for struct members
          // TODO: Handle nested structs in a future pass
        }
      });
    });
  }
}

void CBufferEditor::ApplyEdits()
{
  // Placeholder for task 6.3 - will implement ProxyBuffer creation and replacement
}

void CBufferEditor::ResetAll()
{
  m_Edits.clear();
  RefreshCBuffers();
  m_Ctx.RefreshStatus();
}

void CBufferEditor::ResetVariable(const QModelIndex &index)
{
  // Placeholder for task 6.4 - individual variable reset
  Q_UNUSED(index);
}

void CBufferEditor::ClearAll()
{
  m_Edits.clear();
  m_Model->removeRows(0, m_Model->rowCount());
}

QString CBufferEditor::MakeEditKey(ShaderStage stage, uint32_t slot, uint32_t arrayIdx)
{
  return QString(lit("%1_%2_%3")).arg((int)stage).arg(slot).arg(arrayIdx);
}

void CBufferEditor::MarkModified(QStandardItem *item, bool modified)
{
  QFont font = item->font();
  font.setBold(modified);
  item->setFont(font);

  if(modified)
    item->setBackground(QBrush(QColor(255, 255, 200)));
  else
    item->setBackground(QBrush());
}
