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

#include "TAStatsPanel.h"
#include <QHeaderView>
#include <QSortFilterProxyModel>
#include <QStandardItemModel>
#include "Code/QRDUtils.h"
#include "ui_TAStatsPanel.h"

TAStatsPanel::TAStatsPanel(ICaptureContext &ctx, QWidget *parent)
    : QFrame(parent), ui(new Ui::TAStatsPanel), m_Ctx(ctx)
{
  ui->setupUi(this);

  m_Model = new QStandardItemModel(0, 5, this);
  m_Model->setHorizontalHeaderLabels(
      {tr("Name"), tr("DrawCalls"), tr("Triangles"), tr("Vertices"), tr("Instances")});

  m_ProxyModel = new QSortFilterProxyModel(this);
  m_ProxyModel->setSourceModel(m_Model);
  m_ProxyModel->setFilterCaseSensitivity(Qt::CaseInsensitive);
  m_ProxyModel->setFilterKeyColumn(-1);    // search all columns
#if QT_VERSION >= QT_VERSION_CHECK(5, 10, 0)
  m_ProxyModel->setRecursiveFilteringEnabled(true);
#endif

  ui->statsTree->setModel(m_ProxyModel);
  ui->statsTree->setSortingEnabled(true);
  ui->statsTree->header()->setSectionResizeMode(0, QHeaderView::Stretch);

  m_Ctx.AddCaptureViewer(this);
}

TAStatsPanel::~TAStatsPanel()
{
  m_Ctx.RemoveCaptureViewer(this);
  delete ui;
}

void TAStatsPanel::OnCaptureLoaded()
{
  CollectStats();
}

void TAStatsPanel::OnCaptureClosed()
{
  ClearStats();
}

void TAStatsPanel::on_groupMode_currentIndexChanged(int index)
{
  if(!m_Ctx.IsCaptureLoaded())
    return;

  m_Model->removeRows(0, m_Model->rowCount());

  switch(index)
  {
    case 0: PopulateByPass(); break;
    case 1: PopulateByShader(); break;
    case 2: PopulateByRenderTarget(); break;
  }
}

void TAStatsPanel::on_filterText_textChanged(const QString &text)
{
  m_ProxyModel->setFilterFixedString(text);
}

void TAStatsPanel::on_statsTree_doubleClicked(const QModelIndex &index)
{
  QModelIndex srcIndex = m_ProxyModel->mapToSource(index);
  QStandardItem *item = m_Model->itemFromIndex(srcIndex);
  if(!item)
    return;

  // Store eventId in UserRole
  QVariant eventIdVar = item->data(Qt::UserRole);
  if(eventIdVar.isValid())
  {
    uint32_t eventId = eventIdVar.toUInt();
    m_Ctx.SetEventID({}, eventId, eventId, true);
  }
}

uint64_t TAStatsPanel::CalcTriangles(const ActionDescription &action)
{
  if(!(action.flags & ActionFlags::Drawcall))
    return 0;

  uint32_t numIndices = action.numIndices;
  uint32_t numInstances = qMax(1u, action.numInstances);

  // Topology is not stored in ActionDescription; it lives in pipeline state.
  // As a reasonable approximation, assume triangle lists (3 vertices per primitive).
  // A future pass (task 4.4) will query the replay thread for exact topology.
  uint32_t vertsPerPrim = 3;

  if(numIndices < vertsPerPrim)
    return 0;

  return (uint64_t(numIndices) / vertsPerPrim) * numInstances;
}

void TAStatsPanel::CollectStats()
{
  ClearStats();

  const rdcarray<ActionDescription> &actions = m_Ctx.CurRootActions();

  // Recursive lambda to walk the action tree
  std::function<void(const rdcarray<ActionDescription> &)> walkActions;
  walkActions = [this, &walkActions](const rdcarray<ActionDescription> &actionList) {
    for(const ActionDescription &action : actionList)
    {
      if(action.flags & ActionFlags::Drawcall)
      {
        m_TotalDrawCalls++;
        uint64_t tris = CalcTriangles(action);
        m_TotalTriangles += tris;
        m_TotalVertices += uint64_t(action.numIndices) * qMax(1u, action.numInstances);
        m_TotalInstances += action.numInstances;
      }
      else if(action.flags & (ActionFlags::Dispatch | ActionFlags::DispatchRay))
      {
        m_TotalDispatches++;
      }

      walkActions(action.children);
    }
  };

  walkActions(actions);
  UpdateSummary();
  PopulateByPass();
}

void TAStatsPanel::PopulateByPass()
{
  m_Model->removeRows(0, m_Model->rowCount());

  const rdcarray<ActionDescription> &actions = m_Ctx.CurRootActions();

  // Walk top-level marker groups
  std::function<void(const rdcarray<ActionDescription> &, QStandardItem *)> walkForPass;
  walkForPass = [this, &walkForPass](const rdcarray<ActionDescription> &actionList,
                                     QStandardItem *parentItem) {
    for(const ActionDescription &action : actionList)
    {
      if(action.flags & ActionFlags::PushMarker)
      {
        uint32_t drawCount = 0;
        uint64_t triCount = 0;
        uint64_t vertCount = 0;
        uint64_t instCount = 0;
        uint32_t firstEventId = UINT32_MAX;

        // Count children
        std::function<void(const rdcarray<ActionDescription> &)> countChildren;
        countChildren = [&](const rdcarray<ActionDescription> &children) {
          for(const ActionDescription &child : children)
          {
            if(child.flags & ActionFlags::Drawcall)
            {
              drawCount++;
              triCount += CalcTriangles(child);
              vertCount += uint64_t(child.numIndices) * qMax(1u, child.numInstances);
              instCount += child.numInstances;
              if(child.eventId < firstEventId)
                firstEventId = child.eventId;
            }
            countChildren(child.children);
          }
        };
        countChildren(action.children);

        if(drawCount > 0)
        {
          QList<QStandardItem *> row;
          QStandardItem *nameItem =
              new QStandardItem(QString::fromUtf8(action.customName.c_str()));
          nameItem->setData(firstEventId, Qt::UserRole);
          row.append(nameItem);
          row.append(new QStandardItem(QString::number(drawCount)));
          row.append(new QStandardItem(QString::number(triCount)));
          row.append(new QStandardItem(QString::number(vertCount)));
          row.append(new QStandardItem(QString::number(instCount)));

          if(parentItem)
            parentItem->appendRow(row);
          else
            m_Model->appendRow(row);

          // Recurse for nested markers
          walkForPass(action.children, nameItem);
        }
      }
      else if(action.flags & ActionFlags::Drawcall)
      {
        // Standalone draw not inside a marker
        QList<QStandardItem *> row;
        QStandardItem *nameItem = new QStandardItem(
            action.customName.empty()
                ? QString(lit("Draw %1")).arg(action.eventId)
                : QString::fromUtf8(action.customName.c_str()));
        nameItem->setData(action.eventId, Qt::UserRole);
        row.append(nameItem);
        row.append(new QStandardItem(lit("1")));
        row.append(new QStandardItem(QString::number(CalcTriangles(action))));
        row.append(new QStandardItem(
            QString::number(uint64_t(action.numIndices) * qMax(1u, action.numInstances))));
        row.append(new QStandardItem(QString::number(action.numInstances)));

        if(parentItem)
          parentItem->appendRow(row);
        else
          m_Model->appendRow(row);
      }
    }
  };

  walkForPass(actions, nullptr);
}

void TAStatsPanel::PopulateByShader()
{
  m_Model->removeRows(0, m_Model->rowCount());
  // Shader grouping requires pipeline state for each draw - placeholder for task 4.4
  // Will be filled with replay-thread data collection
}

void TAStatsPanel::PopulateByRenderTarget()
{
  m_Model->removeRows(0, m_Model->rowCount());
  // RT grouping requires pipeline state for each draw - placeholder for task 4.5
  // Will be filled with replay-thread data collection
}

void TAStatsPanel::UpdateSummary()
{
  ui->summaryLabel->setText(
      QString(lit("DrawCalls: %1  |  Triangles: %2  |  Vertices: %3  |  Instances: %4  |  "
                  "Dispatches: %5"))
          .arg(m_TotalDrawCalls)
          .arg(m_TotalTriangles)
          .arg(m_TotalVertices)
          .arg(m_TotalInstances)
          .arg(m_TotalDispatches));
}

void TAStatsPanel::ClearStats()
{
  m_TotalDrawCalls = 0;
  m_TotalTriangles = 0;
  m_TotalVertices = 0;
  m_TotalInstances = 0;
  m_TotalDispatches = 0;
  m_Model->removeRows(0, m_Model->rowCount());
  ui->summaryLabel->setText(QString());
}
